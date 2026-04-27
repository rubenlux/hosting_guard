"""Backup routes — manual backup creation and listing."""
import logging
from fastapi import APIRouter, Depends, HTTPException

from app.api.security import verify_token
from app.infra.audit.hosting_repository import HostingRepository
from app.services.notification_service import notify

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/hosting", tags=["Backup"])

_hosting_repo = HostingRepository()


@router.post("/hostings/{hosting_id}/backup")
async def create_backup(hosting_id: int, user: dict = Depends(verify_token)):
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
