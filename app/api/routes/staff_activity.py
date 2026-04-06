"""
Endpoint de tracking interno para colaboradores.

POST /staff/activity — registra una acción en el log de productividad.
El frontend lo llama en background, transparente para el colaborador.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.api.security import verify_staff_token
from app.infra.audit.staff_repository import StaffRepository

router = APIRouter(tags=["staff-activity"])

_staff_repo = StaffRepository()


def _get_ip(request: Request) -> str:
    for header in ("X-Real-IP", "X-Forwarded-For"):
        val = request.headers.get(header)
        if val:
            return val.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class ActivityRequest(BaseModel):
    action_type: str             # hosting_viewed | file_edited | logs_viewed | …
    description: str
    target_user_id: Optional[int]     = None
    target_hosting_id: Optional[int]  = None
    duration_seconds: Optional[int]   = None


VALID_ACTION_TYPES = {
    "staff_login",
    "support_session_start",
    "support_session_end",
    "hosting_viewed",
    "logs_viewed",
    "file_edited",
    "hosting_restarted",
    "hosting_stopped",
    "hosting_started",
    "issue_resolved",
    "client_note_added",
    "zip_uploaded",
    "file_deleted",
    "metrics_viewed",
}


@router.post("/staff/activity", status_code=201)
def log_staff_activity(
    body: ActivityRequest,
    request: Request,
    payload: dict = Depends(verify_staff_token),
):
    """
    Registra una acción del colaborador en el log de productividad.
    Siempre responde 201 — el frontend no espera el resultado.
    """
    # Aceptar tipos desconocidos para no romper el frontend al agregar eventos nuevos
    action_type = body.action_type if body.action_type in VALID_ACTION_TYPES else "other"

    log_id = _staff_repo.log_activity(
        staff_id=payload["staff_id"],
        action_type=action_type,
        description=body.description[:500],   # truncar descripción larga
        target_user_id=body.target_user_id,
        target_hosting_id=body.target_hosting_id,
        duration_seconds=body.duration_seconds,
        ip_address=_get_ip(request),
    )
    return {"ok": True, "log_id": log_id}
