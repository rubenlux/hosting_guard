"""
Provisioning Gate for HostingGuard static (nginx) tenants.

Runs a series of checks after tenant creation to determine whether the
tenant is actually operational.  Returns a ProvisioningGateResult that
drives the hosting status stored in the DB and what the dashboard shows.

Status hierarchy (from best to worst):
  active                 — all checks pass, real content uploaded
  active_with_placeholder— all checks pass, placeholder content only
  pending_content        — running but no index.html or only placeholder needed
  routing_degraded       — no Traefik File Provider YAML (Docker labels only)
  routing_failed         — 526 / 502 / welcome-to-nginx
  provisioning_failed    — container missing, stopped, or mount misconfigured
"""
import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Patchable in tests
_TRAEFIK_DYNAMIC_DIR = "/opt/traefik-dynamic"
_CLIENTS_DIR = "/opt/clients"

_WELCOME_NGINX_MARKER = "Welcome to nginx"
_PLACEHOLDER_MARKER = "Sitio en configuración"
# HTTP statuses that indicate a hard routing failure (not auth-related)
_ROUTING_FAIL_STATUSES = frozenset({502, 504, 526})


@dataclass
class ProvisioningGateResult:
    ok: bool
    status: str
    checks: dict
    reason: str
    safe_actions: list = field(default_factory=list)
    forbidden_actions: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "status": self.status,
            "checks": self.checks,
            "reason": self.reason,
            "safe_actions": self.safe_actions,
            "forbidden_actions": self.forbidden_actions,
        }


# ── individual checkers ───────────────────────────────────────────────────────

def _check_container(container_name: str, checks: dict) -> None:
    try:
        r = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Status}}", container_name],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            state = r.stdout.strip()
            checks["container_exists"] = True
            checks["container_running"] = state == "running"
    except Exception as exc:
        logger.warning("provisioning_gate: docker inspect failed (%s): %s", container_name, exc)


def _check_mount(container_name: str, host_mount_path: str, checks: dict) -> None:
    checks["host_mount_exists"] = os.path.isdir(host_mount_path)
    try:
        r = subprocess.run(
            ["docker", "inspect", "--format", "{{json .Mounts}}", container_name],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            mounts = json.loads(r.stdout.strip() or "[]")
            for m in mounts:
                if (
                    m.get("Type") == "bind"
                    and m.get("Destination") == "/usr/share/nginx/html"
                    and (m.get("Source") or "").startswith(_CLIENTS_DIR)
                ):
                    checks["container_mount_valid"] = True
                    break
    except Exception as exc:
        logger.warning("provisioning_gate: mount check failed (%s): %s", container_name, exc)


def _check_index_html(host_mount_path: str, checks: dict) -> None:
    index_path = os.path.join(host_mount_path, "index.html")
    if os.path.isfile(index_path):
        checks["index_html_exists"] = True
        try:
            with open(index_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(4096)
            checks["welcome_to_nginx"] = _WELCOME_NGINX_MARKER in content
            checks["placeholder_content"] = _PLACEHOLDER_MARKER in content
        except Exception as exc:
            logger.warning("provisioning_gate: index.html read failed: %s", exc)


def _check_route(hosting_id: int, container_name: str, checks: dict) -> None:
    route_file = os.path.join(_TRAEFIK_DYNAMIC_DIR, f"tenant-{hosting_id}.yml")
    if os.path.isfile(route_file):
        checks["dynamic_file_route_exists"] = True
        try:
            with open(route_file, "r", encoding="utf-8") as f:
                content = f.read()
            checks["uses_forwardauth_file"] = "hg-forwardauth" in content
            # Validate YAML structure — catches middlewares-under-tls bug
            try:
                from app.services.traefik_file_provider import _validate_traefik_yaml
                _validate_traefik_yaml(content, route_file)
                checks["yaml_structure_valid"] = True
            except ValueError as yaml_exc:
                checks["yaml_structure_valid"] = False
                logger.warning("provisioning_gate: invalid YAML structure: %s", yaml_exc)
        except Exception as exc:
            logger.warning("provisioning_gate: route file read failed: %s", exc)
        return
    # Legacy bundle: all tenants in one file (pre-P2B deployments)
    bundle_file = os.path.join(_TRAEFIK_DYNAMIC_DIR, "tenants-active.yml")
    if os.path.isfile(bundle_file):
        try:
            with open(bundle_file, "r", encoding="utf-8") as f:
                bundle_content = f.read()
            if container_name in bundle_content:
                checks["dynamic_file_route_exists"] = True
                checks["uses_bundle_legacy"] = True
                checks["uses_forwardauth_file"] = "hg-forwardauth" in bundle_content
        except Exception as exc:
            logger.warning("provisioning_gate: bundle route check failed: %s", exc)


def _check_http(subdomain: str, container_name: str, checks: dict, timeout: float) -> None:
    try:
        import requests as _req
        r = _req.get(
            f"http://{container_name}:80/",
            timeout=timeout,
            allow_redirects=False,
        )
        checks["origin_http_status"] = r.status_code
    except Exception:
        checks["origin_http_status"] = None

    try:
        import requests as _req
        r = _req.get(f"https://{subdomain}/", timeout=timeout, allow_redirects=True)
        checks["public_http_status"] = r.status_code
    except Exception:
        checks["public_http_status"] = None


# ── evaluator ─────────────────────────────────────────────────────────────────

def _evaluate(checks: dict) -> ProvisioningGateResult:
    """Derive ProvisioningGateResult from a populated checks dict."""
    def _fail(status: str, reason: str, safe=None, forbidden=None):
        return ProvisioningGateResult(
            ok=False, status=status, checks=checks, reason=reason,
            safe_actions=safe or [], forbidden_actions=forbidden or [],
        )

    # ── infrastructure ──────────────────────────────────────────────────────
    if not checks["container_exists"]:
        return _fail("provisioning_failed", "Container not found")

    if not checks["container_running"]:
        return _fail(
            "provisioning_failed", "Container is not running",
            safe=["restart_container"],
        )

    if not checks["host_mount_exists"]:
        return _fail(
            "provisioning_failed", "Host mount directory missing",
            safe=["create_host_mount_dir"],
            forbidden=["write_to_readonly_container_mount"],
        )

    if not checks["container_mount_valid"]:
        return _fail(
            "provisioning_failed",
            "Container bind mount not attached to /usr/share/nginx/html",
            forbidden=["write_to_readonly_container_mount"],
        )

    # ── routing ─────────────────────────────────────────────────────────────
    public_status = checks.get("public_http_status")
    if public_status in _ROUTING_FAIL_STATUSES:
        return _fail(
            "routing_failed",
            f"Public route returns HTTP {public_status}",
            safe=["validate_origin_tls_direct_resolve", "inspect_traefik_acme_logs"],
            forbidden=["disable_tls_verification", "turn_off_cloudflare_security_globally"],
        )

    if checks["welcome_to_nginx"]:
        return _fail(
            "routing_failed",
            "Site shows default nginx welcome page (empty static site)",
            safe=["write_placeholder_index_to_host_mount", "validate_static_index_exists"],
            forbidden=["mark_healthy_on_container_running_only"],
        )

    if not checks["dynamic_file_route_exists"]:
        return _fail(
            "routing_degraded",
            "No Traefik File Provider YAML — route depends on Docker labels only",
            safe=[
                "regenerate_tenant_file_provider_route",
                "migrate_tenant_route_docker_labels_to_file",
                "validate_traefik_dynamic_yaml",
            ],
            forbidden=[
                "rely_on_docker_provider_only",
                "bypass_forwardauth",
                "mark_healthy_without_file_provider_route",
            ],
        )

    if checks.get("yaml_structure_valid") is False:
        return _fail(
            "routing_failed",
            "Traefik route YAML has invalid structure (middlewares nested under tls)",
            safe=["validate_traefik_dynamic_yaml", "regenerate_tenant_file_provider_route"],
            forbidden=["mark_healthy_without_file_provider_route"],
        )

    # ── content ─────────────────────────────────────────────────────────────
    if not checks["index_html_exists"]:
        return _fail(
            "pending_content",
            "No index.html — tenant awaiting content upload",
            safe=["create_placeholder_index_for_empty_static_site", "mark_site_pending_content"],
            forbidden=["mark_healthy_on_container_running_only"],
        )

    if checks.get("placeholder_content"):
        return ProvisioningGateResult(
            ok=True,
            status="active_with_placeholder",
            checks=checks,
            reason="Tenant operational with placeholder — no real content uploaded yet",
        )

    return ProvisioningGateResult(
        ok=True, status="active", checks=checks,
        reason="All provisioning checks passed",
    )


# ── public API ────────────────────────────────────────────────────────────────

def validate_static_tenant_provisioning(
    hosting_id: int,
    container_name: str,
    subdomain: str,
    *,
    check_http: bool = True,
    http_timeout: float = 5.0,
) -> ProvisioningGateResult:
    """Run all provisioning checks for a static (nginx) tenant.

    Set check_http=False when called immediately after container creation,
    since TLS certs and Traefik routing may not be ready yet.
    """
    checks: dict = {
        "container_exists": False,
        "container_running": False,
        "host_mount_exists": False,
        "container_mount_valid": False,
        "index_html_exists": False,
        "welcome_to_nginx": False,
        "placeholder_content": False,
        "dynamic_file_route_exists": False,
        "uses_forwardauth_file": False,
        "yaml_structure_valid": None,  # None=not checked, True=valid, False=invalid
        "origin_http_status": None,
        "public_http_status": None,
    }

    host_mount_path = os.path.join(_CLIENTS_DIR, container_name)

    _check_container(container_name, checks)
    _check_mount(container_name, host_mount_path, checks)
    _check_index_html(host_mount_path, checks)
    _check_route(hosting_id, container_name, checks)
    if check_http:
        _check_http(subdomain, container_name, checks, http_timeout)

    return _evaluate(checks)
