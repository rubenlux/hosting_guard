"""
Internal ForwardAuth endpoint for Traefik.

Traefik calls GET /internal/forwardauth on every inbound request to customer
subdomains, forwarding these headers:
  X-Forwarded-For:  <client-ip>[, proxy1, ...]
  X-Forwarded-Host: <subdomain>.hostingguard.lat
  X-Forwarded-Uri:  <path>?<query>

Response:
  200 — allow the request
  403 — blocked (IP on blocklist, or path blocked by rule)
  429 — rate-limited

This endpoint is network-restricted to the internal Docker network;
no auth token is required.
"""
import logging
import re
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])

_SUBDOMAIN_RE = re.compile(r"^([a-z0-9][a-z0-9-]*)\.hostingguard\.lat$")

_SCANNER_PATHS = frozenset({
    "/wp-login.php",
    "/xmlrpc.php",
    "/.env",
    "/wp-config.php",
    "/phpinfo.php",
    "/shell.php",
    "/.git",
    "/.git/config",
    "/wp-admin/install.php",
})

# Redis cache for subdomain → hosting_id (5 min TTL)
_SUBDOMAIN_CACHE_TTL = 300
_SUBDOMAIN_KEY_FMT   = "hg:subdomain:{subdomain}"


def _extract_ip(forwarded_for: str) -> str:
    return forwarded_for.split(",")[0].strip() if forwarded_for else ""


def _subdomain_from_host(host: str) -> Optional[str]:
    if not host:
        return None
    m = _SUBDOMAIN_RE.match(host.lower())
    return m.group(1) if m else None


def _resolve_hosting_id(subdomain: str) -> Optional[int]:
    """Lookup hosting_id for subdomain, with Redis caching."""
    from app.infra.redis_client import get_redis
    cache_key = _SUBDOMAIN_KEY_FMT.format(subdomain=subdomain)
    r = get_redis()

    if r:
        try:
            cached = r.get(cache_key)
            if cached:
                return int(cached)
        except Exception:
            pass

    hosting_id = _db_hosting_id(subdomain)

    if r and hosting_id is not None:
        try:
            r.setex(cache_key, _SUBDOMAIN_CACHE_TTL, str(hosting_id))
        except Exception:
            pass

    return hosting_id


def _db_hosting_id(subdomain: str) -> Optional[int]:
    from app.infra.db import get_connection, release_connection
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT hosting_id FROM hostings "
            "WHERE subdomain = %s AND status NOT IN ('deleted', 'expired')",
            (subdomain,),
        )
        row = cur.fetchone()
        return row["hosting_id"] if row else None
    except Exception as exc:
        logger.warning("forwardauth: subdomain lookup failed for %s: %s", subdomain, exc)
        return None
    finally:
        release_connection(conn)


@router.get("/forwardauth")
def forwardauth(request: Request):
    """Traefik ForwardAuth handler."""
    fwd_for  = request.headers.get("x-forwarded-for",  "")
    fwd_host = request.headers.get("x-forwarded-host", "")
    fwd_uri  = request.headers.get("x-forwarded-uri",  "/")

    client_ip = _extract_ip(fwd_for)
    subdomain  = _subdomain_from_host(fwd_host)

    if not subdomain:
        return Response(status_code=200)

    try:
        hosting_id = _resolve_hosting_id(subdomain)
    except Exception as exc:
        logger.warning("forwardauth: hosting resolution error subdomain=%s: %s", subdomain, exc)
        return Response(status_code=200)

    if not hosting_id:
        return Response(status_code=200)

    from app.services.security.security_policy_resolver import get_policy
    from app.services.security.ip_blocklist import is_blocked

    try:
        policy = get_policy(hosting_id)
    except Exception as exc:
        logger.warning("forwardauth: policy error hosting_id=%s: %s", hosting_id, exc)
        return Response(status_code=200)

    mode = policy.get("mode", "off")
    if mode == "off":
        return Response(status_code=200)

    path = fwd_uri.split("?")[0].rstrip("/") or "/"

    if mode == "protect":
        # IP blocklist check
        if client_ip:
            block_record = is_blocked(client_ip, hosting_id)
            if block_record:
                rule_id = block_record.get("rule_id", "unknown")
                logger.info(
                    "forwardauth: BLOCKED ip=%s hosting_id=%d rule=%s uri=%s",
                    client_ip, hosting_id, rule_id, fwd_uri,
                )
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Acceso bloqueado por política de seguridad", "rule": rule_id},
                )

        # Path-based rules
        if policy.get("block_xmlrpc") and path == "/xmlrpc.php":
            logger.info("forwardauth: BLOCK xmlrpc ip=%s hosting_id=%d", client_ip, hosting_id)
            return JSONResponse(status_code=403, content={"detail": "xmlrpc.php deshabilitado"})

        if policy.get("block_scanner_paths") and path in _SCANNER_PATHS:
            logger.info(
                "forwardauth: BLOCK scanner path=%s ip=%s hosting_id=%d",
                path, client_ip, hosting_id,
            )
            return JSONResponse(status_code=403, content={"detail": "Ruta bloqueada"})

    if mode == "monitor" and client_ip:
        block_record = is_blocked(client_ip, hosting_id)
        if block_record:
            logger.info(
                "forwardauth: MONITOR (would block) ip=%s hosting_id=%d rule=%s uri=%s",
                client_ip, hosting_id, block_record.get("rule_id", "unknown"), fwd_uri,
            )

    return Response(status_code=200)
