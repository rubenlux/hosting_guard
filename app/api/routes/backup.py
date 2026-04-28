"""Backup routes — manual backup creation, listing, download, delete."""
import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from app.api.rate_limit import limiter
from app.api.security import verify_token
from app.infra.audit.hosting_repository import HostingRepository
from app.services.notification_service import notify

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/hosting", tags=["Backup"])

_hosting_repo = HostingRepository()


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

    try:
        notify(user_id, f"Backup iniciado: {site_name}",
               f"Se está creando un backup de '{site_name}'...",
               category="backup", severity="info", channel="dashboard")
        from app.services.backup_service import create_backup as _create
        result = _create(hosting_id, user_id, container, None,
                         site_name, hosting.get("subdomain", ""))
        if result["status"] == "completed":
            size_mb = result["size_bytes"] / (1024 * 1024)
            notify(user_id, f"Backup completado: {site_name}",
                   f"Backup de '{site_name}' listo ({size_mb:.1f} MB).",
                   category="backup", severity="success", channel="both")
        elif result["errors"]:
            notify(user_id, f"Backup con errores: {site_name}",
                   f"Errores durante el backup: {'; '.join(result['errors'])[:200]}",
                   category="backup", severity="warning", channel="dashboard")
        return result
    except Exception as exc:
        try:
            notify(user_id, f"Backup fallido: {site_name}",
                   f"No se pudo crear el backup: {str(exc)[:150]}",
                   category="backup", severity="critical", channel="both")
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/hostings/{hosting_id}/backups")
def list_backups(hosting_id: int, user: dict = Depends(verify_token)):
    user_id = user["user_id"]
    hosting = _hosting_repo.get_hosting(hosting_id, user_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting not found")
    from app.services.backup_service import list_backups as _list
    return {"items": _list(hosting_id, user_id)}


@router.get("/backups/{backup_id}/download")
@limiter.limit("10/hour")
async def download_backup(
    request: Request,
    backup_id: int,
    background_tasks: BackgroundTasks,
    user: dict = Depends(verify_token),
):
    """Download a completed backup as a tar.gz bundle (manifest + DB + files)."""
    from app.services.backup_service import get_backup, build_download_package

    user_id = int(user["user_id"])
    backup = await asyncio.get_running_loop().run_in_executor(
        None, lambda: get_backup(backup_id, user_id)
    )
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

    loop = asyncio.get_running_loop()
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
    """Delete a failed or partial backup (client can only delete non-completed backups)."""
    from app.services.backup_service import get_backup, delete_backup as _delete

    user_id = int(user["user_id"])
    backup = get_backup(backup_id, user_id)
    if not backup:
        raise HTTPException(status_code=404, detail="Backup no encontrado")
    if backup["status"] == "completed":
        raise HTTPException(
            status_code=403,
            detail="No podés eliminar un backup completado. Contactá soporte si es necesario.",
        )

    _delete(backup_id, user_id=user_id, admin=False)
    return {"status": "deleted", "backup_id": backup_id}
