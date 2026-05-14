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
    """Return static config + file presence for platform routes (no live HTTP check)."""
    from app.services.router_health_guard import PLATFORM_ROUTES, _router_source_for_platform
    out = []
    for route in PLATFORM_ROUTES:
        dfile = route.get("dynamic_file", "")
        out.append({
            "host": route["host"],
            "service": route.get("service"),
            "paths": route.get("paths", []),
            "expected_statuses": route.get("expected_statuses", [200]),
            "dynamic_file": dfile,
            "dynamic_file_exists": os.path.exists(dfile) if dfile else False,
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
