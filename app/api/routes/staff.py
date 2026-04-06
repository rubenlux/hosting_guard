"""
Gestión de colaboradores (staff) y analytics de productividad.

/admin/staff/*  — solo accesible por admin (access_token con role=admin)
/staff/login    — login propio de colaboradores
/staff/me       — perfil del colaborador autenticado
"""
import logging
import secrets
import string
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr

from app.api.security import (
    create_staff_token,
    require_role,
    require_staff_role,
    verify_staff_token,
)
from app.infra.audit.staff_repository import StaffRepository
from app.infra.audit.user_repository import UserRepository

router = APIRouter(tags=["staff"])

_staff_repo = StaffRepository()
_user_repo  = UserRepository()

VALID_ROLES = {"support", "billing", "readonly"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_ip(request: Request) -> str:
    for header in ("X-Real-IP", "X-Forwarded-For"):
        val = request.headers.get(header)
        if val:
            return val.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _generate_temp_password(length: int = 14) -> str:
    # Solo caracteres alfanuméricos sin ambigüedad visual (sin l, 1, I, O, 0)
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CreateStaffRequest(BaseModel):
    email: EmailStr
    full_name: str
    role: str                    # support | billing | readonly


class UpdateStaffRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    full_name: str | None = None


class StaffLoginRequest(BaseModel):
    email: str
    password: str


# ---------------------------------------------------------------------------
# Admin endpoints — gestión de staff
# ---------------------------------------------------------------------------

@router.post("/admin/staff", status_code=status.HTTP_201_CREATED)
def create_staff(
    body: CreateStaffRequest,
    admin: dict = Depends(require_role("admin")),
):
    """Crea una cuenta de colaborador. Devuelve la contraseña temporal (solo una vez)."""
    if body.role not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Rol inválido. Debe ser uno de: {', '.join(sorted(VALID_ROLES))}",
        )

    temp_password = _generate_temp_password()
    pw_hash = bcrypt.hashpw(temp_password.encode(), bcrypt.gensalt()).decode()

    try:
        staff_id = _staff_repo.create_staff(
            admin_id=admin["user_id"],
            email=body.email,
            password_hash=pw_hash,
            full_name=body.full_name,
            role=body.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return {
        "staff_id":      staff_id,
        "email":         body.email,
        "full_name":     body.full_name,
        "role":          body.role,
        "temp_password": temp_password,   # Solo se muestra aquí, una vez
        "message":       "Cuenta creada. Comparte la contraseña temporal de forma segura.",
    }


@router.get("/admin/staff")
def list_staff(admin: dict = Depends(require_role("admin"))):
    """Lista todos los colaboradores con métricas básicas."""
    staff_list = _staff_repo.list_staff()
    # Adjuntar métricas resumidas del último mes
    analytics = {s["staff_id"]: s for s in _staff_repo.get_analytics(days=30)}
    for member in staff_list:
        metrics = analytics.get(member["staff_id"], {})
        member["total_actions_30d"]  = metrics.get("total_actions", 0)
        member["clients_served_30d"] = metrics.get("clients_served", 0)
        member["last_activity_at"]   = metrics.get("last_activity_at")
    return staff_list


@router.patch("/admin/staff/{staff_id}")
def update_staff(
    staff_id: int,
    body: UpdateStaffRequest,
    admin: dict = Depends(require_role("admin")),
):
    """Edita rol, nombre o estado activo de un colaborador."""
    staff = _staff_repo.get_staff_by_id(staff_id)
    if not staff:
        raise HTTPException(status_code=404, detail="Colaborador no encontrado")

    updates = {}
    if body.role is not None:
        if body.role not in VALID_ROLES:
            raise HTTPException(status_code=400, detail=f"Rol inválido: {body.role}")
        updates["role"] = body.role
    if body.is_active is not None:
        updates["is_active"] = 1 if body.is_active else 0
    if body.full_name is not None:
        updates["full_name"] = body.full_name

    _staff_repo.update_staff(staff_id, **updates)
    return {"ok": True, "staff_id": staff_id, "updated": list(updates.keys())}


@router.delete("/admin/staff/{staff_id}")
def deactivate_staff(
    staff_id: int,
    admin: dict = Depends(require_role("admin")),
):
    """Desactiva un colaborador (soft delete). El historial se conserva."""
    staff = _staff_repo.get_staff_by_id(staff_id)
    if not staff:
        raise HTTPException(status_code=404, detail="Colaborador no encontrado")
    _staff_repo.deactivate_staff(staff_id)
    return {"ok": True, "staff_id": staff_id, "message": "Cuenta desactivada. Historial conservado."}


@router.post("/admin/staff/{staff_id}/reset-password")
def reset_staff_password(
    staff_id: int,
    admin: dict = Depends(require_role("admin")),
):
    """Genera una nueva contraseña temporal para el colaborador. Se muestra una sola vez."""
    staff = _staff_repo.get_staff_by_id(staff_id)
    if not staff:
        raise HTTPException(status_code=404, detail="Colaborador no encontrado")

    new_password = _generate_temp_password()
    pw_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    _staff_repo.update_password(staff_id, pw_hash)

    logger.info("Password reset for staff_id=%s by admin=%s", staff_id, admin["email"])

    return {
        "ok":           True,
        "staff_id":     staff_id,
        "email":        staff["email"],
        "new_password": new_password,
        "message":      "Nueva contraseña generada. Compártela de forma segura. Solo se muestra una vez.",
    }


@router.get("/admin/staff/analytics")
def get_team_analytics(
    days: int = 30,
    admin: dict = Depends(require_role("admin")),
):
    """Métricas agregadas de todo el equipo para el período seleccionado."""
    return {
        "days":    days,
        "members": _staff_repo.get_analytics(days=days),
    }


@router.get("/admin/staff/{staff_id}/activity")
def get_staff_activity(
    staff_id: int,
    limit: int = 100,
    admin: dict = Depends(require_role("admin")),
):
    """Historial de actividad de un colaborador específico."""
    staff = _staff_repo.get_staff_by_id(staff_id)
    if not staff:
        raise HTTPException(status_code=404, detail="Colaborador no encontrado")
    activity = _staff_repo.get_activity_for_staff(staff_id, limit=limit)
    hourly   = _staff_repo.get_hourly_activity(staff_id, days=7)
    return {
        "staff":   {k: v for k, v in staff.items() if k != "password_hash"},
        "activity": activity,
        "hourly_distribution": hourly,
    }


# ---------------------------------------------------------------------------
# Staff login — emite staff_token cookie
# ---------------------------------------------------------------------------

@router.post("/staff/login")
def staff_login(
    body: StaffLoginRequest,
    request: Request,
    response: Response,
):
    """Login para colaboradores. Devuelve un staff_token cookie (8h, no renovable)."""
    staff = _staff_repo.get_staff_by_email(body.email)
    if not staff:
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    if not staff.get("is_active"):
        raise HTTPException(status_code=403, detail="Cuenta desactivada. Contacta al administrador.")

    # Normalizar el hash: garantizar que sea str puro sin espacios
    # (PostgreSQL RealDictCursor puede devolver memoryview u otros tipos en algunas versiones)
    stored_hash = staff.get("password_hash") or ""
    if not isinstance(stored_hash, str):
        stored_hash = str(stored_hash)
    stored_hash = stored_hash.strip()

    try:
        password_ok = bcrypt.checkpw(body.password.encode("utf-8"), stored_hash.encode("utf-8"))
    except Exception as exc:
        logger.error("bcrypt.checkpw falló para staff %s: %s", staff.get("staff_id"), exc)
        raise HTTPException(status_code=500, detail="Error interno de autenticación")

    if not password_ok:
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    _staff_repo.update_last_login(staff["staff_id"])

    # Log del login
    _staff_repo.log_activity(
        staff_id=staff["staff_id"],
        action_type="staff_login",
        description="Inicio de sesión",
        ip_address=_get_ip(request),
    )

    token = create_staff_token({
        "staff_id":  staff["staff_id"],
        "email":     staff["email"],
        "full_name": staff["full_name"],
        "role":      staff["role"],
    })

    from app.api.config import APP_ENV
    secure = APP_ENV == "production"
    response.set_cookie(
        key="staff_token",
        value=token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=8 * 3600,
        path="/",
    )

    return {
        "ok":        True,
        "staff_id":  staff["staff_id"],
        "email":     staff["email"],
        "full_name": staff["full_name"],
        "role":      staff["role"],
    }


@router.post("/staff/logout")
def staff_logout(response: Response):
    """Cierra la sesión del colaborador."""
    response.delete_cookie("staff_token", path="/")
    return {"ok": True}


@router.get("/staff/me")
def staff_me(payload: dict = Depends(verify_staff_token)):
    """Perfil del colaborador autenticado."""
    staff = _staff_repo.get_staff_by_id(payload["staff_id"])
    if not staff:
        raise HTTPException(status_code=404, detail="Staff no encontrado")
    return {k: v for k, v in staff.items() if k != "password_hash"}


@router.get("/staff/clients")
def staff_list_clients(payload: dict = Depends(require_staff_role("support", "billing", "readonly"))):
    """Lista de clientes visible para todos los colaboradores autenticados."""
    return _user_repo.get_all_users()


@router.get("/staff/my-activity")
def staff_my_activity(
    limit: int = 50,
    payload: dict = Depends(verify_staff_token),
):
    """Actividad reciente del colaborador autenticado (para su propio dashboard)."""
    return _staff_repo.get_activity_for_staff(payload["staff_id"], limit=limit)
