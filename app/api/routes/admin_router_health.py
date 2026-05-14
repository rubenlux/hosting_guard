"""
Admin API — Router Health Guard (Fase 4A.2)

Endpoints:
  GET  /admin/router-health/platform          — static config view
  POST /admin/router-health/platform/check    — live check, creates incidents
  POST /admin/router-health/platform/repair   — ensure/repair dynamic files (dry_run supported)
  GET  /admin/router-health/tenants           — check + filter results
  POST /admin/router-health/tenants/check     — check (optionally single hosting)
"""
import os
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.security import require_role

router = APIRouter(prefix="/admin/router-health", tags=["admin-router-health"])


class RepairBody(BaseModel):
    dry_run: bool = True


# ─── Platform ─────────────────────────────────────────────────────────────────

@router.get("/platform")
def get_platform_config(_: dict = Depends(require_role("admin"))):
    """Return static config + file visibility for platform routes (no live HTTP check)."""
    from app.services.router_health_guard import (
        PLATFORM_ROUTES, _router_source_for_platform, _dynamic_file_visibility,
    )
    out = []
    for route in PLATFORM_ROUTES:
        dfile = route.get("dynamic_file", "")
        out.append({
            "host": route["host"],
            "service": route.get("service"),
            "paths": route.get("paths", []),
            "expected_statuses": route.get("expected_statuses", [200]),
            "dynamic_file": dfile,
            "dynamic_file_visibility": _dynamic_file_visibility(dfile) if dfile else "absent",
            "router_source": _router_source_for_platform(route),
            "scope": "platform",
        })
    return {"platform_routes": out}


@router.post("/platform/check")
def check_platform(user: dict = Depends(require_role("admin"))):
    """Run live HTTP checks against all platform hosts. Creates incidents for failures."""
    from app.services.router_health_guard import check_platform_routes
    results = check_platform_routes()
    return {
        "results": [r.to_dict() for r in results],
        "total": len(results),
        "healthy": sum(1 for r in results if r.healthy),
        "unhealthy": sum(1 for r in results if not r.healthy),
    }


@router.post("/platform/repair")
def repair_platform(body: RepairBody, user: dict = Depends(require_role("admin"))):
    """
    Ensure/repair platform Traefik dynamic files.
    dry_run=true (default): preview what would change without writing.
    dry_run=false: write files, backup existing if content differs.
    """
    from app.services.router_health_guard import ensure_platform_traefik_routes
    result = ensure_platform_traefik_routes(dry_run=body.dry_run)
    return result


# ─── Tenants ──────────────────────────────────────────────────────────────────

@router.get("/tenants")
def get_tenant_health(
    unhealthy_only: bool = False,
    hosting_id: Optional[int] = None,
    limit: int = 50,
    _: dict = Depends(require_role("admin")),
):
    """Check all active tenant routes. Returns results (optionally filtered)."""
    from app.services.router_health_guard import check_tenant_routes
    results = check_tenant_routes(limit=limit, hosting_id=hosting_id)
    if unhealthy_only:
        results = [r for r in results if not r.healthy]
    return {
        "results": [r.to_dict() for r in results],
        "total": len(results),
        "healthy": sum(1 for r in results if r.healthy),
        "unhealthy": sum(1 for r in results if not r.healthy),
    }


@router.post("/tenants/check")
def check_tenant(
    hosting_id: Optional[int] = None,
    _: dict = Depends(require_role("admin")),
):
    """Check a specific tenant hosting (or all active if hosting_id omitted)."""
    from app.services.router_health_guard import check_tenant_routes
    results = check_tenant_routes(hosting_id=hosting_id)
    return {
        "results": [r.to_dict() for r in results],
        "total": len(results),
        "healthy": sum(1 for r in results if r.healthy),
        "unhealthy": sum(1 for r in results if not r.healthy),
    }


@router.post("/tenants/{hosting_id}/repair")
def repair_tenant(hosting_id: int, body: RepairBody, _: dict = Depends(require_role("admin"))):
    """
    Repair or preview the Traefik dynamic route for a single tenant.

    dry_run=true (default): preview YAML + pre-checks, no disk write.
    dry_run=false: write dynamic file, backup existing, audit log.

    Preconditions (enforced server-side):
      - hosting status must be 'active'
      - container must be running
      - subdomain must be valid
      - /opt/traefik-dynamic must be writable (live write only)

    Error codes in response body:
      traefik_dynamic_path_not_writable — volume not mounted :rw → 409
      container_not_running             — container down       → 400
      hosting_not_active                — hosting stopped      → 400
      path_traversal_blocked            — safety guard         → 400
    """
    from fastapi import HTTPException
    from app.services.router_health_guard import ensure_tenant_traefik_route
    result = ensure_tenant_traefik_route(hosting_id=hosting_id, dry_run=body.dry_run)
    if "error" in result:
        code = result.get("code", "repair_error")
        if code == "traefik_dynamic_path_not_writable":
            raise HTTPException(
                status_code=409,
                detail={
                    "ok": False,
                    "code": code,
                    "message": result["error"],
                    "repair_available": False,
                },
            )
        raise HTTPException(status_code=400, detail={"ok": False, "code": code, "message": result["error"]})
    return result
