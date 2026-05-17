"""Backup routes — manual backup creation, listing, download, delete."""
import asyncio
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.rate_limit import limiter
from app.api.security import verify_token
from app.infra.audit.hosting_repository import HostingRepository
from app.services.notification_service import notify

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/hosting", tags=["Backup"])

_hosting_repo = HostingRepository()


# ── P3A Tenant Backup endpoints ───────────────────────────────────────────────

class TenantBackupRequest(BaseModel):
    backup_type: str = "full"  # full | files | database


@router.post("/hostings/{hosting_id}/backup")
@limiter.limit("4/hour")
async def create_backup(request: Request, hosting_id: int, user: dict = Depends(verify_token)):
    user_id = user["user_id"]
    hosting = _hosting_repo.get_hosting(hosting_id, user_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting not found")
    if hosting.get("status") != "active":
        raise HTTPException(status_code=400, detail="El sitio debe estar activo para crear un backup")

    container = hosting["container_name"]
    site_name = hosting.get("name") or str(hosting_id)

    from app.services.activity_service import log_event as _log
    try:
        notify(user_id, f"Backup iniciado: {site_name}",
               f"Se está creando un backup de '{site_name}'...",
               category="backup", severity="info", channel="dashboard")
        _log(user_id=user_id, hosting_id=hosting_id, event_type="backup_started",
             category="backup", title=f"Backup iniciado: {site_name}",
             ip=request.client.host if request.client else None, source="dashboard")
        from app.services.backup_service import create_backup as _create
        result = _create(hosting_id, user_id, container, None,
                         site_name, hosting.get("subdomain", ""))
        if result["status"] == "completed":
            size_mb = result["size_bytes"] / (1024 * 1024)
            notify(user_id, f"Backup completado: {site_name}",
                   f"Backup de '{site_name}' listo ({size_mb:.1f} MB).",
                   category="backup", severity="success", channel="both")
            _log(user_id=user_id, hosting_id=hosting_id, event_type="backup_completed",
                 category="backup", title=f"Backup completado: {site_name}",
                 message=f"{size_mb:.1f} MB",
                 ip=request.client.host if request.client else None, source="dashboard",
                 metadata={"size_bytes": result["size_bytes"], "backup_id": result.get("backup_id")})
        elif result["errors"]:
            notify(user_id, f"Backup con errores: {site_name}",
                   f"Errores durante el backup: {'; '.join(result['errors'])[:200]}",
                   category="backup", severity="warning", channel="dashboard")
            _log(user_id=user_id, hosting_id=hosting_id, event_type="backup_failed",
                 category="backup", severity="warning",
                 title=f"Backup con errores: {site_name}",
                 message="; ".join(result["errors"])[:200],
                 ip=request.client.host if request.client else None, source="dashboard")
        return result
    except Exception as exc:
        try:
            notify(user_id, f"Backup fallido: {site_name}",
                   f"No se pudo crear el backup: {str(exc)[:150]}",
                   category="backup", severity="critical", channel="both")
            _log(user_id=user_id, hosting_id=hosting_id, event_type="backup_failed",
                 category="backup", severity="warning",
                 title=f"Backup fallido: {site_name}",
                 message=str(exc)[:200],
                 ip=request.client.host if request.client else None, source="dashboard")
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/backups/{backup_id}/download")
@limiter.limit("10/hour")
async def download_backup(
    request: Request,
    backup_id: int,
    background_tasks: BackgroundTasks,
    user: dict = Depends(verify_token),
):
    """Download a completed backup as a tar.gz bundle.
    Checks tenant_backups first, falls back to legacy backups table."""
    from app.services.backup_service import build_download_package

    user_id = int(user["user_id"])
    is_admin = user.get("role") == "admin"
    loop = asyncio.get_running_loop()

    # Try tenant_backups first (P3A/P3B), then legacy backups table
    from app.services.tenant_backup_service import get_tenant_backup
    backup = await loop.run_in_executor(
        None, lambda: get_tenant_backup(backup_id, user_id=None if is_admin else user_id, admin=is_admin)
    )
    if backup:
        # Normalize tenant_backups fields for build_download_package
        backup.setdefault("site_name", backup.get("subdomain"))
        backup.setdefault("created_at", backup.get("started_at"))
        backup["db_path"] = backup.get("database_path")
    else:
        from app.services.backup_service import get_backup
        backup = await loop.run_in_executor(None, lambda: get_backup(backup_id, user_id))

    if not backup:
        raise HTTPException(status_code=404, detail="Backup no encontrado")
    if backup["status"] != "completed":
        raise HTTPException(status_code=400, detail="Solo se pueden descargar backups completados")

    has_any = (
        (backup.get("db_path") and Path(backup["db_path"]).exists()) or
        (backup.get("files_path") and Path(backup["files_path"]).exists())
    )
    if not has_any:
        raise HTTPException(status_code=410, detail="Los archivos de este backup ya no están disponibles")

    tmp_path, filename = await loop.run_in_executor(
        None, lambda: build_download_package(backup)
    )
    background_tasks.add_task(lambda: tmp_path.unlink(missing_ok=True))

    logger.info(
        "backup downloaded: backup_id=%s hosting_id=%s user_id=%s file=%s",
        backup_id, backup["hosting_id"], user_id, filename,
    )
    try:
        from app.services.activity_service import log_event
        log_event(
            user_id=user_id,
            hosting_id=backup["hosting_id"],
            event_type="backup_downloaded",
            category="backup",
            severity="info",
            title=f"Backup descargado: {filename}",
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            source="dashboard",
        )
    except Exception:
        pass
    return FileResponse(
        path=str(tmp_path),
        filename=filename,
        media_type="application/gzip",
    )


@router.delete("/backups/{backup_id}")
def delete_backup(backup_id: int, user: dict = Depends(verify_token)):
    """Delete a failed or partial backup.
    Checks tenant_backups first, falls back to legacy backups table."""
    user_id = int(user["user_id"])
    is_admin = user.get("role") == "admin"

    # Try tenant_backups first (P3A/P3B)
    from app.services.tenant_backup_service import get_tenant_backup, delete_tenant_backup as _del_tenant
    backup = get_tenant_backup(backup_id, user_id=None if is_admin else user_id, admin=is_admin)
    if backup:
        if backup["status"] == "completed":
            raise HTTPException(
                status_code=403,
                detail="No podés eliminar un backup completado. Contactá soporte si es necesario.",
            )
        result = _del_tenant(backup_id, user_id=None if is_admin else user_id, admin=is_admin)
        if result == "protected":
            raise HTTPException(status_code=403, detail="Este backup está protegido.")
    else:
        from app.services.backup_service import get_backup, delete_backup as _delete
        backup = get_backup(backup_id, user_id)
        if not backup:
            raise HTTPException(status_code=404, detail="Backup no encontrado")
        if backup["status"] == "completed":
            raise HTTPException(
                status_code=403,
                detail="No podés eliminar un backup completado. Contactá soporte si es necesario.",
            )
        _delete(backup_id, user_id=user_id, admin=False)

    try:
        from app.services.activity_service import log_event
        log_event(user_id=user_id, hosting_id=backup["hosting_id"],
                  event_type="backup_deleted", category="backup", severity="warning",
                  title=f"Backup eliminado #{backup_id}",
                  source="dashboard",
                  metadata={"backup_id": backup_id, "status_was": backup["status"]})
    except Exception:
        pass
    return {"status": "deleted", "backup_id": backup_id}


# ── P3A: tenant_backups endpoints ─────────────────────────────────────────────

@router.post("/hostings/{hosting_id}/backups")
@limiter.limit("6/hour")
async def create_tenant_backup(
    request: Request,
    hosting_id: int,
    body: TenantBackupRequest = Body(default=TenantBackupRequest()),
    user: dict = Depends(verify_token),
):
    """Trigger a manual backup for a hosting (plan-gated)."""
    user_id = int(user["user_id"])
    is_admin = user.get("role") == "admin"

    # Ownership check (admin bypasses)
    if not is_admin:
        hosting = _hosting_repo.get_hosting(hosting_id, user_id)
        if not hosting:
            raise HTTPException(status_code=404, detail="Hosting not found")
    else:
        hosting = _hosting_repo.get_hosting_any(hosting_id)
        if not hosting:
            raise HTTPException(status_code=404, detail="Hosting not found")

    if body.backup_type not in ("full", "files", "database"):
        raise HTTPException(status_code=400, detail="backup_type must be full, files, or database")

    from app.services.tenant_backup_service import create_tenant_backup as _create
    result = await asyncio.get_running_loop().run_in_executor(
        None,
        lambda: _create(
            hosting_id,
            backup_type=body.backup_type,
            trigger="manual",
            requested_by_user_id=user_id,
            admin_override=is_admin,
        ),
    )

    status = result.get("status")
    if status == "denied":
        raise HTTPException(
            status_code=402,
            detail={
                "code": result.get("error_code"),
                "message": result.get("error_message"),
                "upgrade_required": result.get("upgrade_required", False),
                "recommended_plan": result.get("recommended_plan"),
                "addon": result.get("addon"),
            },
        )
    if status == "failed":
        raise HTTPException(
            status_code=500,
            detail={"code": result.get("error_code"), "message": result.get("error_message")},
        )
    if status == "skipped":
        raise HTTPException(
            status_code=409,
            detail={"code": result.get("error_code"), "message": result.get("error_message")},
        )
    return result


@router.get("/hostings/{hosting_id}/backups")
def list_tenant_backups(hosting_id: int, user: dict = Depends(verify_token)):
    """List backups for a hosting (owner or admin). Non-owner non-admin → 403."""
    user_id = int(user["user_id"])
    is_admin = user.get("role") == "admin"

    if not is_admin:
        hosting = _hosting_repo.get_hosting_any(hosting_id)
        if not hosting:
            raise HTTPException(status_code=404, detail="Hosting not found")
        if hosting.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Acceso denegado")

    from app.services.tenant_backup_service import list_tenant_backups as _list
    try:
        items = _list(hosting_id, user_id=user_id if not is_admin else None, admin=is_admin)
    except Exception:
        items = []
    return {"items": items, "total": len(items)}


@router.get("/hostings/{hosting_id}/backups/{backup_id}")
def get_tenant_backup(hosting_id: int, backup_id: int, user: dict = Depends(verify_token)):
    """Get backup detail (owner or admin)."""
    user_id = int(user["user_id"])
    is_admin = user.get("role") == "admin"

    from app.services.tenant_backup_service import get_tenant_backup as _get
    backup = _get(backup_id, user_id=user_id if not is_admin else None, admin=is_admin)
    if not backup or backup.get("hosting_id") != hosting_id:
        raise HTTPException(status_code=404, detail="Backup not found")
    return backup


@router.delete("/hostings/{hosting_id}/backups/{backup_id}")
def delete_tenant_backup(hosting_id: int, backup_id: int, user: dict = Depends(verify_token)):
    """Delete a backup (owner or admin). Removes files from disk."""
    user_id = int(user["user_id"])
    is_admin = user.get("role") == "admin"

    from app.services.tenant_backup_service import get_tenant_backup as _get, delete_tenant_backup as _del
    backup = _get(backup_id, user_id=user_id if not is_admin else None, admin=is_admin)
    if not backup or backup.get("hosting_id") != hosting_id:
        raise HTTPException(status_code=404, detail="Backup not found")

    if backup.get("status") in ("running", "pending"):
        raise HTTPException(status_code=409, detail="Cannot delete a backup in progress")

    ok = _del(backup_id, user_id=user_id if not is_admin else None, admin=is_admin)
    if not ok:
        raise HTTPException(status_code=404, detail="Backup not found")
    return {"status": "deleted", "backup_id": backup_id}
