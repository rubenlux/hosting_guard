"""
Impersonation / Remote Support endpoints.

POST /admin/impersonate/{user_id}   — admin generates a 15-min support token
GET  /admin/impersonate/sessions    — list active + recent sessions
DELETE /admin/impersonate/{session_id} — revoke a session early
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import jwt

from app.api.security import SECRET, ALGO, require_role, require_staff_role, verify_staff_token, revoke_token
from app.infra.audit.staff_repository import StaffRepository
from app.infra.audit.support_repository import SupportSessionRepository
from app.infra.audit.user_repository import UserRepository

router = APIRouter(prefix="/admin/impersonate", tags=["impersonate"])

_support_repo = SupportSessionRepository()
_user_repo    = UserRepository()
_staff_repo   = StaffRepository()

SUPPORT_TTL_MINUTES = 15


def _get_ip(request: Request) -> str:
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    fwd = request.headers.get("X-Forwarded-For")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/{user_id}")
def start_support_session(
    user_id: int,
    request: Request,
    admin: dict = Depends(require_role("admin")),
):
    """
    Admin initiates a support session for the given user.
    Returns a short-lived token (15 min, non-renewable) with mode=support.
    The token carries the target user's identity so the frontend loads their data.
    """
    target = _user_repo.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    if target.get("role") == "admin":
        raise HTTPException(
            status_code=403,
            detail="No se puede impersonar a otro administrador.",
        )

    ip = _get_ip(request)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=SUPPORT_TTL_MINUTES)
    session_id = _support_repo.create_session(
        admin_id=admin["user_id"],
        target_user_id=user_id,
        expires_at=expires_at,
        ip_address=ip,
    )

    # JWT especial: sub = target user, impersonated_by = admin, mode = support
    payload = {
        "user_id":         user_id,
        "email":           target["email"],
        "role":            target.get("role", "user"),
        "mode":            "support",
        "impersonated_by": admin["user_id"],
        "admin_email":     admin["email"],
        "session_id":      session_id,
        "jti":             str(uuid.uuid4()),
        "type":            "access",
        "exp":             expires_at,
    }
    token = jwt.encode(payload, SECRET, algorithm=ALGO)

    return {
        "token":          token,
        "session_id":     session_id,
        "target_email":   target["email"],
        "expires_at":     expires_at.isoformat(),
        "expires_minutes": SUPPORT_TTL_MINUTES,
    }


@router.get("/sessions")
def list_sessions(admin: dict = Depends(require_role("admin"))):
    """Active sessions + last 50 in history."""
    return {
        "active":  _support_repo.get_active_sessions(),
        "history": _support_repo.get_recent_sessions(limit=50),
    }


@router.delete("/{session_id}")
def revoke_session(
    session_id: str,
    admin: dict = Depends(require_role("admin")),
):
    """Revoke an active support session before it expires naturally."""
    ok = _support_repo.revoke_session(session_id, admin["user_id"])
    if not ok:
        raise HTTPException(
            status_code=404,
            detail="Sesión no encontrada, ya revocada, o no pertenece a este admin.",
        )
    return {"ok": True, "session_id": session_id}


# ---------------------------------------------------------------------------
# Staff support — colaboradores con rol "support" inician sesiones de soporte
# ---------------------------------------------------------------------------

@router.post("/staff/{user_id}", tags=["staff"])
def staff_start_support_session(
    user_id: int,
    request: Request,
    staff: dict = Depends(require_staff_role("support")),
):
    """
    Un colaborador con rol 'support' inicia una sesión de soporte remoto.
    Funciona igual que el admin, pero el token lleva staff_id en lugar de impersonated_by.
    """
    target = _user_repo.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    if target.get("role") == "admin":
        raise HTTPException(status_code=403, detail="No se puede acceder a cuentas de administrador.")

    ip = _get_ip(request)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=SUPPORT_TTL_MINUTES)

    # Usar admin_id=0 como señal de que lo inició un staff (no un admin)
    # El session_id queda en el log para auditoría completa
    session_id = _support_repo.create_session(
        admin_id=staff["staff_id"],   # staff_id actúa como referencia
        target_user_id=user_id,
        expires_at=expires_at,
        ip_address=ip,
    )

    # Registrar en el log de productividad del staff
    _staff_repo.log_activity(
        staff_id=staff["staff_id"],
        action_type="support_session_start",
        description=f"Sesión de soporte iniciada para {target['email']}",
        target_user_id=user_id,
        ip_address=ip,
    )

    payload = {
        "user_id":         user_id,
        "email":           target["email"],
        "role":            target.get("role", "user"),
        "mode":            "support",
        "impersonated_by": staff["staff_id"],
        "admin_email":     staff["email"],
        "session_id":      session_id,
        "jti":             str(uuid.uuid4()),
        "type":            "access",
        "exp":             expires_at,
        "initiated_by":    "staff",
    }
    token = jwt.encode(payload, SECRET, algorithm=ALGO)

    return {
        "token":           token,
        "session_id":      session_id,
        "target_email":    target["email"],
        "expires_at":      expires_at.isoformat(),
        "expires_minutes": SUPPORT_TTL_MINUTES,
    }
