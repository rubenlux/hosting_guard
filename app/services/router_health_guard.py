"""
Router Health Guard — Fase 4A.2

Detects missing/broken Traefik routes for platform and tenant hosting.
Optionally auto-repairs platform dynamic files when REPAIR_MODE='protect'.

Scope:
  Platform: hostingguard.lat, www.hostingguard.lat, api.hostingguard.lat
  Tenants:  all active hostings with subdomain + container_name

Safety contract:
  - Never touches client code, files, DNS, certificates, or billing.
  - Tenant routes: read-only (incidents only, no auto-repair).
  - Platform dynamic files: idempotent write + backup-before-overwrite.
"""
import hashlib
import json
import logging
import os
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_USER_AGENT = "HostingGuard-RouterHealth/1.0"
_HTTP_TIMEOUT = 10
# Traefik's default 404 body is "404 page not found" = 19 bytes
_TRAEFIK_404_MAX_BODY = 30
_BASE_DOMAIN = "hostingguard.lat"
# Patchable in tests
_TRAEFIK_DYNAMIC_DIR = "/opt/traefik-dynamic"


def normalize_tenant_public_host(subdomain: str, base_domain: str = _BASE_DOMAIN) -> str:
    """
    Normalize a subdomain/FQDN from the DB to a public hostname.
    Handles: already-FQDN, bare slug, mixed case, protocol prefix, trailing slashes, custom domains.
    Never produces *.base_domain.base_domain.
    """
    s = subdomain.strip().lower()
    for prefix in ("https://", "http://"):
        if s.startswith(prefix):
            s = s[len(prefix):]
    s = s.split("/")[0].split("?")[0].split(":")[0]
    if s.endswith("." + base_domain) or s == base_domain:
        return s
    if "." in s:
        return s
    return f"{s}.{base_domain}"


def _dynamic_file_visibility(path: str) -> str:
    """
    Returns 'visible', 'not_mounted_in_app', or 'absent'.
    'not_mounted_in_app': parent dir absent → volume not mounted in this container.
    'absent': dir exists but specific file does not (file genuinely missing on host).
    """
    if not path:
        return "absent"
    if os.path.exists(path):
        return "visible"
    if not os.path.exists(os.path.dirname(path)):
        return "not_mounted_in_app"
    return "absent"

PLATFORM_ROUTES = [
    {
        "host": "hostingguard.lat",
        "paths": ["/", "/login", "/dashboard"],
        "expected_statuses": [200],
        "expected_content_type_contains": "text/html",
        "service": "frontend",
        "dynamic_file": "/opt/traefik-dynamic/platform-frontend.yml",
    },
    {
        "host": "www.hostingguard.lat",
        "paths": ["/"],
        "expected_statuses": [200, 301, 302],
        "service": "frontend",
        "dynamic_file": "/opt/traefik-dynamic/platform-frontend.yml",
    },
    {
        "host": "api.hostingguard.lat",
        "paths": ["/health"],
        "expected_statuses": [200],
        "expected_content_type_contains": "application/json",
        "service": "hosting_guard",
        "dynamic_file": "/opt/traefik-dynamic/platform-api.yml",
    },
]

_PLATFORM_FRONTEND_YAML = """\
# platform-frontend.yml
# Managed by router_health_guard.py — do not edit manually.
# Backup before editing: cp platform-frontend.yml platform-frontend.yml.bak
#
# Routes: hostingguard.lat + www.hostingguard.lat → frontend:80
# No ForwardAuth — SPA handles auth client-side.

http:
  routers:
    platform-frontend:
      rule: "Host(`hostingguard.lat`) || Host(`www.hostingguard.lat`)"
      entryPoints:
        - websecure
      service: platform-frontend
      tls:
        certResolver: le
      priority: 100

  services:
    platform-frontend:
      loadBalancer:
        servers:
          - url: "http://frontend:80"
"""

_PLATFORM_API_YAML = """\
# platform-api.yml
# Managed by router_health_guard.py — do not edit manually.
# Backup before editing: cp platform-api.yml platform-api.yml.bak
#
# Route: api.hostingguard.lat → hosting_guard:8000
# No ForwardAuth — FastAPI handles JWT auth internally.
# NEVER add hg-forwardauth here — it creates an infinite loop.

http:
  routers:
    platform-api:
      rule: "Host(`api.hostingguard.lat`)"
      entryPoints:
        - websecure
      service: platform-api
      tls:
        certResolver: le
      priority: 100

  services:
    platform-api:
      loadBalancer:
        servers:
          - url: "http://hosting_guard:8000"
        responseForwarding:
          flushInterval: "100ms"
"""

_TENANT_FORWARDAUTH_YAML = """\
# tenant-forwardauth-middleware.yml
# Managed by router_health_guard.py — do not edit manually.
#
# Defines hg-forwardauth via the FILE provider so tenant routers remain reachable
# even when Traefik's Docker provider is unavailable (version mismatch, socket issue, etc.).
#
# Reference in tenant file routers: hg-forwardauth@file
# (NOT @docker — that qualifier only works when Docker provider is functional)
#
# NEVER add this middleware to platform-api.yml — it would create a ForwardAuth loop.

http:
  middlewares:
    hg-forwardauth:
      forwardAuth:
        address: "http://hosting_guard:8000/internal/forwardauth"
        trustForwardHeader: true
"""

_PLATFORM_FILES = {
    "/opt/traefik-dynamic/platform-frontend.yml": _PLATFORM_FRONTEND_YAML,
    "/opt/traefik-dynamic/platform-api.yml": _PLATFORM_API_YAML,
    "/opt/traefik-dynamic/tenant-forwardauth-middleware.yml": _TENANT_FORWARDAUTH_YAML,
}


@dataclass
class RouterHealthResult:
    host: str
    scope: str  # "platform" | "tenant"
    hosting_id: Optional[int] = None
    container_name: Optional[str] = None
    expected_status: str = "active"
    container_running: Optional[bool] = None
    router_source: str = "unknown"  # "dynamic_file" | "docker_labels" | "missing" | "unknown"
    dynamic_file_visibility: Optional[str] = None  # "visible" | "not_mounted_in_app" | "absent"
    public_status_code: Optional[int] = None
    content_type: Optional[str] = None
    healthy: bool = False
    incident_type: Optional[str] = None
    summary: str = ""
    evidence: dict = field(default_factory=dict)
    checked_at: str = ""

    def to_dict(self) -> dict:
        return {
            "host": self.host,
            "hosting_id": self.hosting_id,
            "container_name": self.container_name,
            "scope": self.scope,
            "expected_status": self.expected_status,
            "container_running": self.container_running,
            "router_source": self.router_source,
            "dynamic_file_visibility": self.dynamic_file_visibility,
            "public_status_code": self.public_status_code,
            "content_type": self.content_type,
            "healthy": self.healthy,
            "incident_type": self.incident_type,
            "summary": self.summary,
            "evidence": self.evidence,
            "checked_at": self.checked_at,
        }


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _context_hash(host: str, hosting_id: Optional[int], incident_type: str, container_name: Optional[str]) -> str:
    data = {"host": host, "hosting_id": hosting_id, "incident_type": incident_type, "container_name": container_name}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]


_NGINX_DEFAULT_MARKERS = (b"Welcome to nginx!", b"nginx default page")
_NGINX_403_MARKERS = (b"403 Forbidden", b"<center>nginx</center>", b"<center>nginx/")


def _is_nginx_default_page(body: bytes) -> bool:
    return any(marker in body for marker in _NGINX_DEFAULT_MARKERS)


def _is_nginx_403_empty_dir(body: bytes) -> bool:
    """True when nginx returns its own 403 page (empty/missing index.html).
    Distinguishes from ForwardAuth 403 which has a different body."""
    return all(marker in body for marker in (b"403 Forbidden", b"nginx"))


def _http_check(url: str, timeout: int = _HTTP_TIMEOUT) -> tuple:
    """
    Returns (status_code, content_type, body_bytes).
    Special codes: -1 = timeout, -2 = SSL/TLS error, 0 = connection refused/DNS error.
    """
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            body = resp.read(512)
            return resp.status, resp.headers.get("content-type", ""), body
    except urllib.error.HTTPError as e:
        body = e.read(256)
        ct = e.headers.get("content-type", "") if e.headers else ""
        return e.code, ct, body
    except urllib.error.URLError as e:
        reason = str(e.reason) if hasattr(e, "reason") else str(e)
        if "SSL" in reason or "certificate" in reason.lower():
            return -2, "", b""
        if "timed out" in reason.lower():
            return -1, "", b""
        return 0, "", b""
    except TimeoutError:
        return -1, "", b""
    except OSError:
        return 0, "", b""


def _classify_failure(status_code: int, content_type: str, body: bytes = b"") -> str:
    if status_code == -2:
        return "tls_or_certificate_issue"
    if status_code in (-1, 0):
        return "public_route_timeout"
    if status_code == 404:
        return "traefik_router_missing_or_unmatched"
    if status_code == 403 and _is_nginx_403_empty_dir(body):
        return "nginx_403_empty_index"
    if status_code == 526:
        # Cloudflare: Invalid SSL certificate on origin — ACME/TLS propagation failure
        return "tls_or_certificate_issue"
    if status_code in (502, 503, 504):
        return "traefik_backend_unreachable"
    return "traefik_backend_unreachable"


def _container_status(container_name: str) -> Optional[bool]:
    """Returns True=running, False=exists but stopped, None=not found/error."""
    try:
        from app.infra.docker_client import run_docker_command
        rc, out, _ = run_docker_command(
            ["inspect", "--format", "{{.State.Status}}", container_name], timeout=5
        )
        if rc != 0:
            return None
        return out.strip() == "running"
    except Exception:
        return None


def _container_image(container_name: str) -> str:
    """Returns the container's image name, or '' on error."""
    try:
        from app.infra.docker_client import run_docker_command
        rc, out, _ = run_docker_command(
            ["inspect", "--format", "{{.Config.Image}}", container_name], timeout=5
        )
        return out.strip() if rc == 0 else ""
    except Exception:
        return ""


def _get_container_mounts(container_name: str) -> list:
    """Returns list of mount dicts from docker inspect, or [] on error."""
    try:
        from app.infra.docker_client import run_docker_command
        rc, out, _ = run_docker_command(
            ["inspect", "--format", "{{json .Mounts}}", container_name], timeout=5
        )
        if rc != 0:
            return []
        return json.loads(out.strip()) or []
    except Exception:
        return []


def _has_html_mount(mounts: list) -> bool:
    """True if any mount targets /usr/share/nginx/html."""
    return any(m.get("Destination") == "/usr/share/nginx/html" for m in mounts)


def _router_source_for_platform(route_cfg: dict) -> str:
    dfile = route_cfg.get("dynamic_file", "")
    if dfile and os.path.exists(dfile):
        return "dynamic_file"
    service = route_cfg.get("service", "")
    if service:
        try:
            from app.infra.docker_client import run_docker_command
            rc, out, _ = run_docker_command(
                ["inspect", "--format", "{{index .Config.Labels \"traefik.enable\"}}", service],
                timeout=5,
            )
            if rc == 0 and out.strip() == "true":
                return "docker_labels"
        except Exception:
            pass
    return "missing"


def _router_source_for_tenant(hosting_id: int, container_name: str) -> str:
    # Individual file — current canonical form
    if os.path.exists(f"{_TRAEFIK_DYNAMIC_DIR}/tenant-{hosting_id}.yml"):
        return "dynamic_file"
    # Legacy alt name (pre-namespacing)
    if os.path.exists(f"{_TRAEFIK_DYNAMIC_DIR}/{hosting_id}.yml"):
        return "dynamic_file"
    # Legacy bundle: multiple tenants in one file (pre-P2B deployments)
    bundle = f"{_TRAEFIK_DYNAMIC_DIR}/tenants-active.yml"
    if os.path.exists(bundle):
        try:
            with open(bundle, "r", encoding="utf-8") as _f:
                if container_name in _f.read():
                    return "dynamic_file_bundle"
        except Exception:
            pass
    try:
        from app.infra.docker_client import run_docker_command
        rc, out, _ = run_docker_command(
            ["inspect", "--format", "{{index .Config.Labels \"traefik.enable\"}}", container_name],
            timeout=5,
        )
        if rc == 0 and out.strip() == "true":
            return "docker_labels"
    except Exception:
        pass
    return "missing"


# ─── Public API ───────────────────────────────────────────────────────────────

def check_single_host(host: str, expected_service: Optional[str] = None) -> "RouterHealthResult":
    """
    Performs a full check for a single host.
    Looks up PLATFORM_ROUTES config if it's a platform host; otherwise checks '/' with tenant defaults.
    """
    route_cfg = next((r for r in PLATFORM_ROUTES if r["host"] == host), None)

    if route_cfg:
        paths = route_cfg["paths"]
        expected_statuses = route_cfg["expected_statuses"]
        expected_ct = route_cfg.get("expected_content_type_contains")
        router_source = _router_source_for_platform(route_cfg)
        scope = "platform"
    else:
        paths = ["/"]
        expected_statuses = [200, 301, 302, 401, 403]
        expected_ct = None
        router_source = "unknown"
        scope = "tenant"

    for path in paths:
        status_code, content_type, body = _http_check(f"https://{host}{path}")
        if status_code not in expected_statuses:
            incident_type = _classify_failure(status_code, content_type)
            return RouterHealthResult(
                host=host,
                scope=scope,
                router_source=router_source,
                public_status_code=status_code,
                content_type=content_type,
                healthy=False,
                incident_type=incident_type,
                summary=f"{host}{path} → HTTP {status_code} ({incident_type})",
                evidence={"host": host, "path": path, "status_code": status_code,
                          "content_type": content_type, "body_size": len(body),
                          "expected_service": expected_service or route_cfg and route_cfg.get("service")},
                checked_at=_now_iso(),
            )

    return RouterHealthResult(
        host=host,
        scope=scope,
        router_source=router_source,
        public_status_code=status_code,
        content_type=content_type,
        healthy=True,
        summary=f"{host} — OK",
        checked_at=_now_iso(),
    )


def check_platform_routes() -> list:
    """
    Check all platform routes. Creates system_incidents for unhealthy routes.
    Returns list[RouterHealthResult] — one per platform host.
    """
    results = []
    for route_cfg in PLATFORM_ROUTES:
        host = route_cfg["host"]
        paths = route_cfg["paths"]
        expected_statuses = route_cfg["expected_statuses"]
        router_source = _router_source_for_platform(route_cfg)
        dfile = route_cfg.get("dynamic_file", "")
        dfile_visibility = _dynamic_file_visibility(dfile)

        failing_path = None
        failing_status = None
        failing_ct = None
        failing_body = None
        incident_type = None
        last_status = None
        last_ct = ""

        for path in paths:
            status_code, content_type, body = _http_check(f"https://{host}{path}")
            last_status = status_code
            last_ct = content_type
            if status_code not in expected_statuses:
                failing_path = path
                failing_status = status_code
                failing_ct = content_type
                failing_body = len(body)
                incident_type = _classify_failure(status_code, content_type)
                break

        if incident_type is None:
            result = RouterHealthResult(
                host=host,
                scope="platform",
                router_source=router_source,
                dynamic_file_visibility=dfile_visibility,
                public_status_code=last_status,
                content_type=last_ct,
                healthy=True,
                summary=f"{host} — todos los paths responden correctamente",
                checked_at=_now_iso(),
            )
        else:
            evidence = {
                "host": host,
                "path": failing_path,
                "status_code": failing_status,
                "content_type": failing_ct,
                "body_size": failing_body,
                "router_source": router_source,
                "expected_service": route_cfg.get("service"),
                "dynamic_file": dfile,
                "dynamic_file_visibility": dfile_visibility,
            }
            result = RouterHealthResult(
                host=host,
                scope="platform",
                router_source=router_source,
                dynamic_file_visibility=dfile_visibility,
                public_status_code=failing_status,
                content_type=failing_ct,
                healthy=False,
                incident_type=incident_type,
                summary=f"{host}{failing_path} → HTTP {failing_status} ({incident_type})",
                evidence=evidence,
                checked_at=_now_iso(),
            )
            _emit_platform_incident(result)

        results.append(result)

    return results


def check_tenant_routes(limit: int = 100, hosting_id: Optional[int] = None) -> list:
    """
    Check public routes for active tenant hostings.
    Creates incidents for failures. Never auto-repairs.
    Returns list[RouterHealthResult].
    """
    from app.infra.db import get_connection, release_connection

    conn = None
    hostings = []
    try:
        conn = get_connection()
        cur = conn.cursor()
        _MONITORED_STATUSES = (
            "active", "active_with_placeholder", "pending_content",
            "routing_degraded", "routing_failed", "provisioning_failed",
        )
        if hosting_id is not None:
            cur.execute(
                """
                SELECT hosting_id, user_id, subdomain, container_name,
                       COALESCE(db_container_name, '') AS db_container_name
                FROM hostings
                WHERE status = ANY(%s)
                  AND hosting_id = %s
                  AND subdomain IS NOT NULL AND subdomain <> ''
                  AND container_name IS NOT NULL AND container_name <> ''
                """,
                (list(_MONITORED_STATUSES), hosting_id),
            )
        else:
            cur.execute(
                """
                SELECT hosting_id, user_id, subdomain, container_name,
                       COALESCE(db_container_name, '') AS db_container_name
                FROM hostings
                WHERE status = ANY(%s)
                  AND subdomain IS NOT NULL AND subdomain <> ''
                  AND container_name IS NOT NULL AND container_name <> ''
                ORDER BY hosting_id
                LIMIT %s
                """,
                (list(_MONITORED_STATUSES), limit),
            )
        hostings = [dict(r) for r in cur.fetchall()]
    except Exception as exc:
        logger.error("router_health_guard: DB query failed: %s", exc)
    finally:
        if conn:
            release_connection(conn)

    results = []
    for h in hostings:
        try:
            results.append(_check_tenant_hosting(h))
        except Exception as exc:
            logger.warning("router_health_guard: tenant check failed for %s: %s", h.get("subdomain"), exc)
    return results


def _check_tenant_hosting(h: dict) -> "RouterHealthResult":
    hosting_id = h["hosting_id"]
    subdomain = h["subdomain"]
    container_name = h["container_name"]
    user_id = h.get("user_id")
    db_container_name = (h.get("db_container_name") or "").strip()
    is_static = not db_container_name
    host = normalize_tenant_public_host(subdomain)

    container_running = _container_status(container_name)
    router_source = _router_source_for_tenant(hosting_id, container_name)

    incident_type = None
    evidence: dict = {
        "host": host,
        "hosting_id": hosting_id,
        "container_name": container_name,
        "container_running": container_running,
        "router_source": router_source,
    }

    if container_running is not True:
        incident_type = "container_not_running"
        summary = (
            f"{host} — contenedor '{container_name}' no está running"
            if container_running is False
            else f"{host} — contenedor '{container_name}' no encontrado"
        )
    else:
        # ForwardAuth returns 401/302 for unauthenticated users — all are valid signs the route works.
        # 403 is accepted here but post-checked below: nginx 403 (empty dir) is unhealthy,
        # ForwardAuth 403 (auth required) is healthy.
        expected_statuses = [200, 301, 302, 401, 403]
        status_code, content_type, body = _http_check(f"https://{host}/")
        evidence["status_code"] = status_code
        evidence["content_type"] = content_type
        evidence["body_size"] = len(body)

        if status_code not in expected_statuses:
            incident_type = _classify_failure(status_code, content_type, body)
            summary = f"{host} → HTTP {status_code} ({incident_type})"
        elif status_code == 403 and _is_nginx_403_empty_dir(body):
            incident_type = "nginx_403_empty_index"
            summary = f"{host} → HTTP 403 nginx directorio vacío (tenant empty content — NO index.html)"
        elif status_code == 200 and _is_nginx_default_page(body):
            incident_type = "misconfigured_site_content"
            summary = f"{host} → HTTP 200 pero sirve página nginx por defecto (sin contenido)"
        elif router_source == "docker_labels":
            # Site is reachable but File Provider YAML is missing — routing_degraded.
            # Docker labels routing survives only while Docker provider is healthy;
            # File Provider is the authoritative model.
            incident_type = "tenant_route_docker_labels_only"
            summary = (
                f"{host} → HTTP {status_code} OK "
                f"(File Provider YAML missing — Docker labels only routing)"
            )
        elif router_source == "dynamic_file_bundle":
            # Routed via legacy tenants-active.yml bundle — functional but needs migration
            # to individual tenant-{id}.yml. Not an incident; flag in evidence only.
            evidence["legacy_bundle"] = True
            summary = f"{host} → HTTP {status_code} OK (legacy bundle — individual YAML migration needed)"
        else:
            summary = f"{host} → HTTP {status_code} OK"

        # ── ProvisioningGate enrichment (static/nginx tenants only) ──────────
        # Run gate with check_http=False (HTTP already checked above) to get
        # filesystem + mount + route checks. The gate is the canonical source
        # of truth for provisioning state; its result enriches evidence and
        # can set incident_type when HTTP check alone is insufficient.
        if is_static:
            try:
                from app.services.provisioning_gate import validate_static_tenant_provisioning
                gate = validate_static_tenant_provisioning(
                    hosting_id, container_name, subdomain, check_http=False,
                )
                evidence["gate_status"] = gate.status
                evidence["gate_checks"] = gate.checks
                if gate.safe_actions:
                    evidence["gate_safe_actions"] = gate.safe_actions
                if gate.forbidden_actions:
                    evidence["gate_forbidden_actions"] = gate.forbidden_actions
                # Gate supersedes HTTP result for routing/content failures only.
                # provisioning_failed is excluded: _container_status already handles
                # that above, and gate docker inspect may fail in restricted envs.
                if not gate.ok and incident_type is None:
                    _GATE_INCIDENT_MAP = {
                        "routing_degraded": "tenant_route_docker_labels_only",
                        "pending_content":  "nginx_403_empty_index",
                    }
                    mapped = _GATE_INCIDENT_MAP.get(gate.status)
                    if mapped:
                        incident_type = mapped
                        summary = f"{host} — gate: {gate.reason}"
            except Exception as _gate_exc:
                logger.debug(
                    "router_health_guard: gate enrichment failed for hosting_id=%s: %s",
                    hosting_id, _gate_exc,
                )

    healthy = incident_type is None
    result = RouterHealthResult(
        host=host,
        hosting_id=hosting_id,
        container_name=container_name,
        scope="tenant",
        container_running=container_running,
        router_source=router_source,
        public_status_code=evidence.get("status_code"),
        content_type=evidence.get("content_type"),
        healthy=healthy,
        incident_type=incident_type,
        summary=summary,
        evidence=evidence,
        checked_at=_now_iso(),
    )

    if not healthy:
        _emit_tenant_incident(result, user_id)
    else:
        try:
            _resolve_tenant_router_incidents(
                hosting_id,
                status_code_after=evidence.get("status_code"),
                container_running=container_running,
                router_source=router_source,
            )
        except Exception:
            pass

    return result


# ─── Incident emission ────────────────────────────────────────────────────────

def _enrich_incident_with_runbook(incident_type: str, summary: str) -> dict:
    """Look up a runbook by incident_type or summary text; return fields for evidence."""
    try:
        from app.services.incidents.incident_knowledge_service import (
            match_error_signature, search_runbooks,
        )
        # Try exact signature match on summary first, then incident_type keyword
        matches = match_error_signature(summary) if summary else []
        if not matches:
            matches = match_error_signature(incident_type)
        if not matches:
            matches = search_runbooks(incident_type)
        if not matches:
            return {}
        best = matches[0]
        return {
            "matched_runbook_id": best.incident_id,
            "runbook_confidence": best.confidence,
            "runbook_match_method": best.match_method,
            "auto_repair_allowed": best.auto_repair_allowed,
            "safe_actions": best.safe_actions,
            "forbidden_actions": best.forbidden_actions,
        }
    except Exception:
        return {}


def _emit_platform_incident(result: RouterHealthResult) -> None:
    from app.infra.db import get_connection, release_connection
    from app.services.incidents.incident_deduper import _upsert_incident

    correlation_key = f"platform_route:{result.incident_type}:{result.host}"
    runbook_fields = _enrich_incident_with_runbook("platform_route_unhealthy", result.summary or "")
    evidence = {**(result.evidence or {}), **runbook_fields}
    conn = None
    try:
        conn = get_connection()
        _upsert_incident(
            conn,
            source_table="router_health_guard",
            source_id=f"platform:{result.host}",
            source_type="router_health",
            correlation_key=correlation_key,
            incident_type="platform_route_unhealthy",
            severity="critical",
            hosting_id=None,
            user_id=None,
            title=f"Ruta pública de plataforma no saludable — {result.host}",
            summary=result.summary,
            evidence=evidence,
        )
        conn.commit()
    except Exception as exc:
        logger.error("router_health_guard: platform incident failed: %s", exc)
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
    finally:
        if conn:
            release_connection(conn)


def _emit_tenant_incident(result: RouterHealthResult, user_id: Optional[int]) -> None:
    from app.infra.db import get_connection, release_connection
    from app.services.incidents.incident_deduper import _upsert_incident

    chash = _context_hash(result.host, result.hosting_id, result.incident_type or "", result.container_name)
    correlation_key = f"router_health:{result.incident_type}:{result.host}:{chash}"
    runbook_fields = _enrich_incident_with_runbook(
        result.incident_type or "traefik_router_missing_or_unmatched",
        result.summary or "",
    )
    evidence = {**(result.evidence or {}), **runbook_fields}

    conn = None
    try:
        conn = get_connection()
        _upsert_incident(
            conn,
            source_table="router_health_guard",
            source_id=f"tenant:{result.hosting_id}:{result.host}",
            source_type="router_health",
            correlation_key=correlation_key,
            incident_type=result.incident_type or "traefik_router_missing_or_unmatched",
            severity="critical",
            hosting_id=result.hosting_id,
            user_id=user_id,
            title=f"Sitio de cliente inaccesible públicamente — {result.host}",
            summary=result.summary,
            evidence=evidence,
        )
        conn.commit()
    except Exception as exc:
        logger.error("router_health_guard: tenant incident failed for %s: %s", result.host, exc)
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
    finally:
        if conn:
            release_connection(conn)


# ─── Platform route ensure (idempotent write) ─────────────────────────────────

def ensure_platform_traefik_routes(dry_run: bool = False) -> dict:
    """
    Creates or updates platform Traefik dynamic YAML files.
    Backs up existing files before overwriting when content differs.

    Returns:
        {"dry_run": bool, "changed": bool, "files": {path: {"action": "created"|"updated"|"unchanged"}}}
    """
    DYNAMIC_DIR = "/opt/traefik-dynamic"
    BACKUP_DIR = os.path.join(DYNAMIC_DIR, "backups")
    file_results: dict = {}
    changed = False

    for path, content in _PLATFORM_FILES.items():
        if not os.path.exists(path):
            action = "created"
            existing = ""
        else:
            try:
                with open(path) as f:
                    existing = f.read()
            except OSError:
                existing = ""
            action = "updated" if existing != content else "unchanged"

        if action != "unchanged":
            changed = True
            if not dry_run:
                if action == "updated":
                    os.makedirs(BACKUP_DIR, exist_ok=True)
                    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                    bak = os.path.join(BACKUP_DIR, f"{os.path.basename(path)}.{ts}")
                    try:
                        with open(bak, "w") as f:
                            f.write(existing)
                    except OSError as exc:
                        logger.warning("router_health_guard: backup write failed %s: %s", bak, exc)

                os.makedirs(DYNAMIC_DIR, exist_ok=True)
                with open(path, "w") as f:
                    f.write(content)
                logger.info("router_health_guard: %s %s", action, path)

        file_results[path] = {"action": action}

    result = {"dry_run": dry_run, "changed": changed, "files": file_results}

    if not dry_run and changed:
        _log_audit_event("platform_traefik_route_ensured", result)
    elif dry_run and changed:
        _log_audit_event("platform_routes_repair_dry_run", {**result, "dry_run": True})

    return result


# ─── Audit logging ────────────────────────────────────────────────────────────

def _log_audit_event(event_type: str, payload: dict) -> None:
    from app.infra.db import get_connection, release_connection
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO orchestrator_events
                (container_name, user_id, event_type, message, created_at, simulated)
            VALUES ('platform', NULL, %s, %s, NOW(), 0)
            """,
            (event_type, json.dumps(payload)),
        )
        conn.commit()
    except Exception as exc:
        logger.debug("router_health_guard: audit log failed (%s): %s", event_type, exc)
    finally:
        if conn:
            release_connection(conn)


# ─── Tenant router repair ─────────────────────────────────────────────────────

_TRAEFIK_DYNAMIC_DIR = "/opt/traefik-dynamic"
# Platform files that tenant repair must never touch.
_PLATFORM_PROTECTED_FILES = {
    "platform-frontend.yml",
    "platform-api.yml",
    "tenant-forwardauth-middleware.yml",
}


def _traefik_dir_writable() -> bool:
    """Return True if TRAEFIK_DYNAMIC_DIR exists and is writable from this container."""
    return os.path.isdir(_TRAEFIK_DYNAMIC_DIR) and os.access(_TRAEFIK_DYNAMIC_DIR, os.W_OK)


def ensure_tenant_traefik_route(hosting_id: int, dry_run: bool = True) -> dict:
    """
    Creates or updates the Traefik dynamic YAML for a tenant hosting.

    Safety contract:
      - Only writes tenant-{hosting_id}.yml; never touches platform-*.yml.
      - Path traversal is impossible: hosting_id is always an int.
      - Live write validates directory is mounted writable before touching disk.
      - Backs up existing file before overwriting.
      - dry_run=True: preview only, no disk access required.

    Returns:
        {"dry_run", "hosting_id", "host", "container_name", "action", "yaml", "file_path",
         "repair_available": True}
        or {"error": str, "code": str, "repair_available": bool}
    """
    from app.infra.db import get_connection, release_connection

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT hosting_id, user_id, subdomain, container_name, status FROM hostings WHERE hosting_id = %s",
            (hosting_id,),
        )
        row = cur.fetchone()
    except Exception as exc:
        logger.error("ensure_tenant_route: DB error: %s", exc)
        return {"error": f"DB error: {exc}", "code": "db_error", "repair_available": False}
    finally:
        if conn:
            release_connection(conn)

    if not row:
        return {"error": "Hosting not found", "code": "hosting_not_found", "repair_available": False}

    h = dict(row)
    if h["status"] != "active":
        return {
            "error": f"Hosting status is '{h['status']}', must be 'active'",
            "code": "hosting_not_active",
            "repair_available": False,
        }

    subdomain = (h.get("subdomain") or "").strip()
    container_name = (h.get("container_name") or "").strip()
    if not subdomain or not container_name:
        return {
            "error": "Hosting missing subdomain or container_name",
            "code": "hosting_incomplete",
            "repair_available": False,
        }

    host = normalize_tenant_public_host(subdomain)

    container_running = _container_status(container_name)
    if not container_running:
        status_str = "stopped" if container_running is False else "not found"
        return {
            "error": f"Container '{container_name}' is {status_str}. Resolve container first.",
            "code": "container_not_running",
            "repair_available": False,
        }

    # ── Writability pre-check (live write only) ───────────────────────────────
    # dry_run never touches disk, so skip the check — UI "Simular reparación" must
    # always work even when the volume is not mounted writable.
    if not dry_run and not _traefik_dir_writable():
        return {
            "error": (
                "The app container cannot write Traefik dynamic files. "
                f"Mount {_TRAEFIK_DYNAMIC_DIR} as writable (:rw) in docker-compose, "
                "or run the host-level repair script instead."
            ),
            "code": "traefik_dynamic_path_not_writable",
            "repair_available": False,
        }

    # ── Build YAML + safe file path ───────────────────────────────────────────
    router_name = f"tenant-{hosting_id}"
    yaml_content = (
        f"# tenant-{hosting_id}.yml\n"
        f"# Managed by router_health_guard.py — do not edit manually.\n"
        f"# Route: {host} → {container_name}:80\n"
        f"# ForwardAuth: hg-forwardauth@file (file provider — survives Docker provider failure)\n\n"
        f"http:\n"
        f"  routers:\n"
        f"    {router_name}:\n"
        f"      rule: \"Host(`{host}`)\"\n"
        f"      entryPoints:\n"
        f"        - websecure\n"
        f"      service: {router_name}\n"
        f"      tls:\n"
        f"        certResolver: le\n"
        f"      middlewares:\n"
        f"        - hg-forwardauth@file\n"
        f"      priority: 50\n\n"
        f"  services:\n"
        f"    {router_name}:\n"
        f"      loadBalancer:\n"
        f"        servers:\n"
        f"          - url: \"http://{container_name}:80\"\n"
    )

    # hosting_id is always an int (FastAPI type-enforces at the API layer),
    # so tenant-{hosting_id}.yml can never traverse the path. Explicit guard anyway.
    filename = f"tenant-{hosting_id}.yml"
    if filename in _PLATFORM_PROTECTED_FILES or os.sep in filename or filename.startswith("."):
        return {
            "error": "Refusing to write: filename collides with protected platform file.",
            "code": "path_traversal_blocked",
            "repair_available": False,
        }
    file_path = os.path.join(_TRAEFIK_DYNAMIC_DIR, filename)

    existing_content = ""
    file_exists = os.path.exists(file_path)
    if file_exists:
        try:
            with open(file_path) as f:
                existing_content = f.read()
        except OSError:
            existing_content = ""

    action = "unchanged" if (file_exists and existing_content == yaml_content) else (
        "updated" if file_exists else "created"
    )

    result = {
        "dry_run": dry_run,
        "hosting_id": hosting_id,
        "host": host,
        "container_name": container_name,
        "action": action,
        "yaml": yaml_content,
        "file_path": file_path,
        "repair_available": True,
    }

    if action == "unchanged" or dry_run:
        return result

    # ── Live write ────────────────────────────────────────────────────────────
    BACKUP_DIR = os.path.join(_TRAEFIK_DYNAMIC_DIR, "backups")
    try:
        if action == "updated":
            os.makedirs(BACKUP_DIR, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            bak = os.path.join(BACKUP_DIR, f"tenant-{hosting_id}.yml.{ts}")
            try:
                with open(bak, "w") as f:
                    f.write(existing_content)
            except OSError as exc:
                logger.warning("ensure_tenant_route: backup failed %s: %s", bak, exc)

        os.makedirs(_TRAEFIK_DYNAMIC_DIR, exist_ok=True)
        with open(file_path, "w") as f:
            f.write(yaml_content)
    except OSError as exc:
        logger.error("ensure_tenant_route: write failed %s: %s", file_path, exc)
        return {
            "error": (
                f"Failed to write {file_path}: {exc}. "
                f"Ensure {_TRAEFIK_DYNAMIC_DIR} is mounted writable in the app container."
            ),
            "code": "traefik_dynamic_path_not_writable",
            "repair_available": False,
        }

    logger.info("router_health_guard: tenant route %s %s", action, file_path)
    _log_audit_event("tenant_router_repaired", {
        "hosting_id": hosting_id,
        "host": host,
        "container_name": container_name,
        "file_path": file_path,
        "action": action,
    })

    return result


def _resolve_tenant_router_incidents(
    hosting_id: int,
    *,
    status_code_after: Optional[int] = None,
    container_running: Optional[bool] = None,
    router_source: Optional[str] = None,
) -> None:
    """
    Resolve all open router_health incidents for a tenant that is now healthy.

    Uses _query() (returns list[dict]) to avoid KeyError(0) on RealDictCursor rows.
    Filters by source_type='router_health' (set by all _emit_*_incident callers).
    """
    from app.infra.db import get_connection, release_connection
    from app.services.incidents.incident_deduper import _resolve_incident, _query

    recovery_evidence: dict = {
        "resolved_reason": "router_health_recovered",
        "recovered_at": _now_iso(),
    }
    if status_code_after is not None:
        recovery_evidence["status_code_after"] = status_code_after
    if container_running is not None:
        recovery_evidence["container_running_after"] = container_running
    if router_source is not None:
        recovery_evidence["route_source_after"] = router_source

    conn = None
    try:
        conn = get_connection()
        rows = _query(
            conn,
            """
            SELECT correlation_key FROM system_incidents
            WHERE source_type = 'router_health'
              AND status = 'open'
              AND hosting_id = %s
            """,
            (hosting_id,),
        )
        resolved = 0
        for row in rows:
            if _resolve_incident(conn, row["correlation_key"], extra_evidence=recovery_evidence):
                resolved += 1
        if resolved:
            conn.commit()
            logger.info(
                "router_health_guard: resolved %d incident(s) for hosting_id=%s (recovered)",
                resolved, hosting_id,
            )
    except Exception as exc:
        logger.warning(
            "router_health_guard: incident resolve failed for hosting_id=%s: %s",
            hosting_id, exc,
        )
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
    finally:
        if conn:
            release_connection(conn)


# ─── Traefik Docker provider health ──────────────────────────────────────────

_TRAEFIK_API_URLS = [
    "http://traefik:8080/api/providers",
    "http://traefik:9000/api/providers",
]


def _check_traefik_docker_provider() -> dict:
    """
    Try to reach Traefik's internal API and verify Docker provider is present.

    Returns:
        {"status": "ok"}                 — Docker provider found and functional
        {"status": "missing"}            — Traefik API up, Docker provider absent
        {"status": "api_unavailable"}    — Cannot reach Traefik API (not exposed or wrong port)
        {"status": "api_error", "error"} — API reachable but response unexpected
    """
    for api_url in _TRAEFIK_API_URLS:
        try:
            req = urllib.request.Request(api_url, headers={"User-Agent": _USER_AGENT})
            with urllib.request.urlopen(req, timeout=3) as resp:
                raw = resp.read(8192)
            try:
                data = json.loads(raw)
            except Exception:
                return {"status": "api_error", "error": "non-json response from Traefik API"}
            if "docker" in data:
                return {"status": "ok", "providers": list(data.keys())}
            return {"status": "missing", "providers": list(data.keys())}
        except urllib.error.URLError:
            continue
        except Exception as exc:
            return {"status": "api_error", "error": str(exc)}
    return {"status": "api_unavailable"}


def _emit_docker_provider_incident(unhealthy_count: int, total_tenants: int, api_status: str) -> None:
    """Create a system_incidents row when Docker provider appears to have failed."""
    from app.infra.db import get_connection, release_connection
    from app.services.incidents.incident_deduper import _upsert_incident

    correlation_key = "router_health:traefik_docker_provider_unhealthy:system"
    runbook_fields = _enrich_incident_with_runbook("traefik_docker_provider_unhealthy", "")
    evidence = {
        "unhealthy_tenants": unhealthy_count,
        "total_tenants": total_tenants,
        "traefik_api_status": api_status,
        "recommended_fix": (
            "Set DOCKER_API_VERSION=1.44 on docker-socket-proxy "
            "or upgrade tecnativa/docker-socket-proxy. "
            "Then restart Traefik container."
        ),
        **runbook_fields,
    }
    conn = None
    try:
        conn = get_connection()
        _upsert_incident(
            conn,
            source_table="router_health_guard",
            source_id="platform:traefik_docker_provider",
            source_type="router_health",
            correlation_key=correlation_key,
            incident_type="traefik_docker_provider_unhealthy",
            severity="critical",
            hosting_id=None,
            user_id=None,
            title="Traefik Docker provider no responde — routers de tenants caídos",
            summary=(
                f"{unhealthy_count}/{total_tenants} tenants inaccesibles públicamente. "
                f"Probable fallo del Docker provider de Traefik (API status: {api_status}). "
                "Verificar versión del socket proxy y reiniciar Traefik."
            ),
            evidence=evidence,
        )
        conn.commit()
    except Exception as exc:
        logger.error("router_health_guard: docker provider incident failed: %s", exc)
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
    finally:
        if conn:
            release_connection(conn)


# ─── Static container mount health + safe remediation ────────────────────────

_PLAN_RESOURCES: dict = {
    "free":     {"cpu": "0.5", "memory": "512m"},
    "personal": {"cpu": "1.0", "memory": "1g"},
    "negocio":  {"cpu": "2.0", "memory": "2g"},
    "agencia":  {"cpu": "4.0", "memory": "4g"},
    "basic":    {"cpu": "0.5", "memory": "512m"},
    "pro":      {"cpu": "1.0", "memory": "1g"},
    "business": {"cpu": "2.0", "memory": "2g"},
}


def check_static_container_mounts() -> list:
    """
    Detects active nginx (static) hostings whose container has no bind mount on
    /usr/share/nginx/html but whose client files exist on the host.

    Emits invalid_container_mount incidents. Never modifies containers.
    """
    from app.infra.db import get_connection, release_connection

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT hosting_id, user_id, subdomain, container_name
            FROM hostings
            WHERE status = 'active'
              AND (db_container_name IS NULL OR db_container_name = '')
            ORDER BY hosting_id
            """,
        )
        rows = [dict(r) for r in cur.fetchall()]
    except Exception as exc:
        logger.error("check_static_container_mounts: DB error: %s", exc)
        return []
    finally:
        if conn:
            release_connection(conn)

    results = []
    for h in rows:
        container_name = (h.get("container_name") or "").strip()
        if not container_name:
            continue

        image = _container_image(container_name)
        if "nginx" not in image.lower():
            continue

        client_index = f"/opt/clients/{container_name}/index.html"
        if not os.path.exists(client_index):
            continue

        mounts = _get_container_mounts(container_name)
        if _has_html_mount(mounts):
            continue

        host = normalize_tenant_public_host(h.get("subdomain", ""))
        result = RouterHealthResult(
            host=host,
            hosting_id=h["hosting_id"],
            container_name=container_name,
            scope="tenant",
            container_running=_container_status(container_name) is True,
            router_source="unknown",
            healthy=False,
            incident_type="invalid_container_mount",
            summary=(
                f"{host} — contenedor sin mount en /usr/share/nginx/html "
                f"(archivos del cliente presentes en host, contenido no servido)"
            ),
            evidence={
                "container_name": container_name,
                "image": image,
                "mounts": mounts,
                "client_index": client_index,
            },
            checked_at=_now_iso(),
        )
        _emit_tenant_incident(result, h.get("user_id"))
        results.append(result)

    return results


def ensure_static_container_mount(hosting_id: int, dry_run: bool = True) -> dict:
    """
    Recreates a static nginx container with the correct read-only bind mount.

    Preconditions (all enforced server-side):
      - hosting status == 'active'
      - container image contains 'nginx'
      - db_container_name is empty (not WordPress)
      - /opt/clients/{container_name}/index.html exists on the host
      - mount not already present

    dry_run=True  — validate preconditions + preview, no changes.
    dry_run=False — docker stop → docker rm → docker run with -v :ro.
    Audit: tenant_container_recreated_with_static_mount
    """
    from app.infra.db import get_connection, release_connection

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT hosting_id, user_id, subdomain, container_name, status, plan, db_container_name
            FROM hostings WHERE hosting_id = %s
            """,
            (hosting_id,),
        )
        row = cur.fetchone()
    except Exception as exc:
        return {"error": f"DB error: {exc}", "code": "db_error", "repair_available": False}
    finally:
        if conn:
            release_connection(conn)

    if not row:
        return {"error": "Hosting not found", "code": "hosting_not_found", "repair_available": False}

    h = dict(row)

    if h["status"] != "active":
        return {
            "error": f"Hosting status is '{h['status']}', must be 'active'",
            "code": "hosting_not_active",
            "repair_available": False,
        }

    db_container = (h.get("db_container_name") or "").strip()
    if db_container:
        return {
            "error": "WordPress hosting — static mount repair does not apply",
            "code": "not_static_hosting",
            "repair_available": False,
        }

    container_name = (h.get("container_name") or "").strip()
    if not container_name:
        return {"error": "Hosting has no container_name", "code": "hosting_incomplete", "repair_available": False}

    image = _container_image(container_name)
    if "nginx" not in image.lower():
        return {
            "error": f"Container image '{image}' is not nginx — static repair only applies to nginx containers",
            "code": "not_nginx_container",
            "repair_available": False,
        }

    client_dir = f"/opt/clients/{container_name}"
    client_index = os.path.join(client_dir, "index.html")
    if not os.path.exists(client_index):
        return {
            "error": f"No index.html at {client_index} — upload site content before repairing mount",
            "code": "no_client_content",
            "repair_available": False,
        }

    mounts = _get_container_mounts(container_name)
    if _has_html_mount(mounts):
        return {
            "ok": True,
            "dry_run": dry_run,
            "action": "already_correct",
            "message": "Container already has /usr/share/nginx/html mount — no action needed",
            "container_name": container_name,
            "repair_available": False,
        }

    plan = (h.get("plan") or "free").lower()
    resources = _PLAN_RESOURCES.get(plan, _PLAN_RESOURCES["free"])
    mount_spec = f"{client_dir}:/usr/share/nginx/html:ro"

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "action": "would_recreate",
            "container_name": container_name,
            "image": image,
            "mount": mount_spec,
            "resources": resources,
            "message": "Dry run — no changes made. Set dry_run=false to apply.",
        }

    try:
        from app.infra.docker_client import run_docker_command, TENANT_NETWORK

        run_docker_command(["stop", container_name], timeout=15)
        run_docker_command(["rm", container_name], timeout=10)

        rc, _, err = run_docker_command([
            "run", "-d",
            "--name", container_name,
            "--network", TENANT_NETWORK,
            "--restart", "unless-stopped",
            "--cpus", resources["cpu"],
            "--memory", resources["memory"],
            "-v", mount_spec,
            "nginx:alpine",
        ], timeout=30)

        if rc != 0:
            return {"error": f"docker run failed: {err}", "code": "docker_run_failed", "repair_available": True}

        _log_audit_event(
            "tenant_container_recreated_with_static_mount",
            {"hosting_id": hosting_id, "container_name": container_name, "mount": mount_spec},
        )

        return {
            "ok": True,
            "dry_run": False,
            "action": "recreated",
            "container_name": container_name,
            "mount": mount_spec,
            "repair_available": False,
        }
    except Exception as exc:
        return {"error": f"Repair failed: {exc}", "code": "repair_error", "repair_available": True}


# ─── Scheduler job ────────────────────────────────────────────────────────────

def router_health_guard_job() -> None:
    """
    Periodic job registered in scheduler_runner.
    Platform: detect + auto-repair when REPAIR_MODE='protect'.
    Tenants:  detect + create incidents, no auto-repair.
    """
    from app.services.router_repair_policy import REPAIR_MODE

    logger.info("router_health_guard_job: starting (REPAIR_MODE=%s)", REPAIR_MODE)
    _log_audit_event("router_health_check_started", {"scope": "platform+tenant"})

    # ── Platform ──────────────────────────────────────────────────────────────
    platform_results = []
    try:
        platform_results = check_platform_routes()
        unhealthy_platform = [r for r in platform_results if not r.healthy]

        if unhealthy_platform:
            logger.warning(
                "router_health_guard_job: platform unhealthy hosts=%s",
                [r.host for r in unhealthy_platform],
            )
            _log_audit_event(
                "router_health_unhealthy_detected",
                {"scope": "platform", "hosts": [r.host for r in unhealthy_platform]},
            )
            if REPAIR_MODE == "protect":
                try:
                    repair = ensure_platform_traefik_routes(dry_run=False)
                    if repair["changed"]:
                        repaired = sum(1 for f in repair["files"].values() if f["action"] != "unchanged")
                        logger.warning("router_health_guard: auto-repaired %d platform file(s)", repaired)
                        _log_audit_event("platform_routes_repaired", repair)
                except Exception as exc:
                    logger.error("router_health_guard: platform auto-repair failed: %s", exc)
            elif REPAIR_MODE == "monitor":
                _log_audit_event("platform_routes_repair_dry_run", {"decision": "would_repair"})
    except Exception as exc:
        logger.error("router_health_guard: platform check failed: %s", exc)

    # ── Tenants ───────────────────────────────────────────────────────────────
    tenant_results = []
    try:
        tenant_results = check_tenant_routes()
        unhealthy_tenants = [r for r in tenant_results if not r.healthy]
        for r in unhealthy_tenants:
            _log_audit_event(
                "tenant_router_repair_skipped_policy",
                {"host": r.host, "hosting_id": r.hosting_id, "incident_type": r.incident_type},
            )
    except Exception as exc:
        logger.error("router_health_guard: tenant check failed: %s", exc)

    # ── Docker provider heuristic ─────────────────────────────────────────────
    # If >= 3 tenants fail with "router missing" simultaneously, the Docker provider
    # is likely down (all tenant routers are defined via Docker labels by default).
    # Try Traefik API to confirm, then emit a platform-level incident.
    try:
        router_missing = [
            r for r in tenant_results
            if not r.healthy and r.incident_type == "traefik_router_missing_or_unmatched"
        ]
        if len(router_missing) >= 3 and len(tenant_results) > 0:
            api_status_info = _check_traefik_docker_provider()
            api_status = api_status_info.get("status", "unknown")
            # "missing" confirms Docker provider gone; "api_unavailable" is inconclusive
            # but multiple tenants down is already a strong signal either way.
            if api_status in ("missing", "api_unavailable", "ok"):
                logger.warning(
                    "router_health_guard_job: %d/%d tenants with router_missing — "
                    "possible Docker provider failure (Traefik API: %s)",
                    len(router_missing), len(tenant_results), api_status,
                )
                _emit_docker_provider_incident(len(router_missing), len(tenant_results), api_status)
    except Exception as exc:
        logger.error("router_health_guard: docker provider heuristic failed: %s", exc)

    # ── Static container mount check ──────────────────────────────────────────
    mount_results = []
    try:
        mount_results = check_static_container_mounts()
        if mount_results:
            logger.warning(
                "router_health_guard_job: %d static container(s) with missing html mount",
                len(mount_results),
            )
    except Exception as exc:
        logger.error("router_health_guard: static mount check failed: %s", exc)

    healthy_p = sum(1 for r in platform_results if r.healthy)
    healthy_t = sum(1 for r in tenant_results if r.healthy)
    unhealthy_t = len(tenant_results) - healthy_t
    logger.info(
        "router_health_guard_job: done — platform=%d/%d ok, tenants=%d/%d ok, "
        "unhealthy_tenants=%d, invalid_mounts=%d",
        healthy_p, len(platform_results), healthy_t, len(tenant_results),
        unhealthy_t, len(mount_results),
    )
    _log_audit_event("router_health_check_completed", {"scope": "platform+tenant"})
