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

Fail-open contract:
  - Errors resolving hosting (DB down, unknown subdomain) → 200
  - Errors reading policy (DB/Redis) → 200
  - Errors reading blocklist (Redis down) → 200
  Never block legitimate traffic due to an infrastructure error.

Logging contract:
  Every request emits exactly ONE structured log line:
    event=forwardauth_decision hosting_id=<id> ip=<ip> mode=<mode>
    blocklist_hit=<bool> decision=<allow|block|would_block|rate_limit>
    reason=<reason>
  The try/finally block guarantees this even on early returns.
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

_SUBDOMAIN_CACHE_TTL = 300
_SUBDOMAIN_KEY_FMT   = "hg:subdomain:{subdomain}"


def _extract_valid_ip(forwarded_for: str) -> str:
    """Return the first non-empty, non-'unknown' token from X-Forwarded-For."""
    if not forwarded_for:
        return ""
    for token in forwarded_for.split(","):
        ip = token.strip()
        if ip and ip.lower() != "unknown":
            return ip
    return ""


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
        if not row:
            return None
        return row["hosting_id"] if hasattr(row, "keys") else row[0]
    except Exception as exc:
        logger.warning("forwardauth: subdomain lookup failed for %s: %s", subdomain, exc)
        return None
    finally:
        release_connection(conn)


def _log_decision(
    *,
    event: str,
    host: str,
    hosting_id: Optional[int],
    ip: str,
    uri: str,
    protection_mode: str,
    blocklist_hit: bool,
    rule_id: str,
    decision: str,
    reason: str,
) -> None:
    logger.info(
        "forwardauth event=%s host=%s hosting_id=%s ip=%s uri=%s mode=%s "
        "blocklist_hit=%s rule_id=%s decision=%s reason=%s",
        event, host, hosting_id, ip, uri, protection_mode,
        blocklist_hit, rule_id, decision, reason,
    )


@router.get("/forwardauth")
def forwardauth(request: Request):
    """Traefik ForwardAuth handler."""
    fwd_for  = request.headers.get("x-forwarded-for",  "")
    fwd_host = request.headers.get("x-forwarded-host", "")
    fwd_uri  = request.headers.get("x-forwarded-uri",  "/")

    client_ip = _extract_valid_ip(fwd_for)
    subdomain  = _subdomain_from_host(fwd_host)

    # Decision context — updated along every code path; logged unconditionally
    # in the finally block so that every request produces exactly one log line.
    _ctx: dict = {
        "hosting_id":   None,
        "mode":         "unknown",
        "blocklist_hit": False,
        "rule_id":      "",
        "decision":     "allow",
        "reason":       None,   # None → not decided yet; set "pass" at final return
    }

    try:
        if not subdomain:
            _ctx["reason"] = "unknown_subdomain"
            return Response(status_code=200)

        try:
            hosting_id = _resolve_hosting_id(subdomain)
        except Exception as exc:
            logger.warning("forwardauth: hosting resolution error subdomain=%s: %s", subdomain, exc)
            _ctx["reason"] = "hosting_lookup_error"
            return Response(status_code=200)

        _ctx["hosting_id"] = hosting_id

        if not hosting_id:
            _ctx["reason"] = "hosting_not_found"
            return Response(status_code=200)

        from app.services.security.security_policy_resolver import get_policy
        from app.services.security.ip_blocklist import (
            is_ip_blocked_for_hosting,
            is_route_blocked_for_hosting,
        )

        try:
            policy = get_policy(hosting_id)
        except Exception as exc:
            logger.warning("forwardauth: policy error hosting_id=%s: %s", hosting_id, exc)
            _ctx["reason"] = "policy_error"
            return Response(status_code=200)

        mode = policy.get("mode", "off")
        _ctx["mode"] = mode
        path = fwd_uri.split("?")[0].rstrip("/") or "/"

        if mode == "off":
            _ctx["reason"] = "protection_off"
            return Response(status_code=200)

        # IP blocklist check — runs in BOTH protect and monitor modes.
        # Monitor: logs would_block but never returns 403.
        block_record = None
        if client_ip:
            try:
                block_record = is_ip_blocked_for_hosting(client_ip, hosting_id)
            except Exception as exc:
                logger.warning(
                    "forwardauth: ip_blocklist check failed ip=%s hosting_id=%s: %s",
                    client_ip, hosting_id, exc,
                )
                block_record = None  # fail-open

        if block_record:
            rule_id = block_record.get("rule_id", "unknown")
            _ctx.update({"blocklist_hit": True, "rule_id": rule_id})
            if mode == "protect":
                _ctx.update({"decision": "block", "reason": "ip_blocked"})
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Acceso bloqueado por política de seguridad", "rule": rule_id},
                )
            # monitor mode: record would_block and fall through to allow
            _ctx.update({"decision": "would_block", "reason": "ip_blocked_monitor"})

        if mode == "protect":
            # Rate-limit block (auto-remediation temporary_rate_limit)
            if client_ip:
                try:
                    rate_block = is_route_blocked_for_hosting(f"rate_limit:{client_ip}", hosting_id)
                except Exception as exc:
                    logger.warning(
                        "forwardauth: rate_limit check failed ip=%s hosting_id=%s: %s",
                        client_ip, hosting_id, exc,
                    )
                    rate_block = None  # fail-open

                if rate_block:
                    rule_id = rate_block.get("rule_id", "rate_limit")
                    _ctx.update({
                        "blocklist_hit": True, "rule_id": rule_id,
                        "decision": "rate_limit", "reason": "rate_limit_block",
                    })
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Rate limit temporal activo", "rule": rule_id},
                    )

            # xmlrpc check: policy setting OR auto-remediation route block
            if path == "/xmlrpc.php":
                try:
                    xmlrpc_route_blocked = is_route_blocked_for_hosting("xmlrpc", hosting_id)
                except Exception:
                    xmlrpc_route_blocked = None  # fail-open

                if policy.get("block_xmlrpc") or xmlrpc_route_blocked:
                    _ctx.update({
                        "blocklist_hit": True, "rule_id": "xmlrpc_block",
                        "decision": "block", "reason": "xmlrpc_disabled",
                    })
                    return JSONResponse(status_code=403, content={"detail": "xmlrpc.php deshabilitado"})

            # Scanner paths check
            if policy.get("block_scanner_paths") and path in _SCANNER_PATHS:
                _ctx.update({
                    "blocklist_hit": True, "rule_id": "scanner_path",
                    "decision": "block", "reason": "scanner_path_blocked",
                })
                return JSONResponse(status_code=403, content={"detail": "Ruta bloqueada"})

        # Final allow — only set reason if nothing else did
        if _ctx["reason"] is None:
            _ctx["reason"] = "pass"
        return Response(status_code=200)

    finally:
        _log_decision(
            event="forwardauth_decision",
            host=fwd_host,
            hosting_id=_ctx["hosting_id"],
            ip=client_ip,
            uri=fwd_uri,
            protection_mode=_ctx["mode"],
            blocklist_hit=_ctx["blocklist_hit"],
            rule_id=_ctx["rule_id"],
            decision=_ctx["decision"],
            reason=_ctx["reason"] or "unknown",
        )
