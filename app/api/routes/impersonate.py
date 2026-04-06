"""
Impersonation / Remote Support endpoints.

CRITICAL ROUTE ORDER: FastAPI matches routes top-to-bottom.
All literal-prefix routes (/sessions/*, /staff/*) MUST be registered
BEFORE generic parameterized routes (/{user_id}, /{session_id}/close)
to prevent "staff" or "sessions" being parsed as integers -> 422/500.

Route map:
  POST   /admin/impersonate/staff/{user_id}          staff starts support session
  POST   /admin/impersonate/staff/{session_id}/close  staff closes session
  GET    /admin/impersonate/sessions                  list sessions (admin)
  GET    /admin/impersonate/sessions/{session_id}     session detail (admin)
  POST   /admin/impersonate/{user_id}                 admin starts support session
  POST   /admin/impersonate/{session_id}/close        admin closes session
  DELETE /admin/impersonate/{session_id}              admin revokes session
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from jose import jwt
from pydantic import BaseModel

from app.api.security import SECRET, ALGO, require_role, require_staff_role
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


# ── Models ────────────────────────────────────────────────────────────────────

class StartSupportRequest(BaseModel):
    issue_description: Optional[str] = None
    origin: str = "manual"   # manual | client_request | ai_advisory | scheduled


class CloseSessionRequest(BaseModel):
    result: str                          # resolved | unresolved | escalated | ongoing
    resolution_notes: Optional[str] = None
    action_taken: Optional[str] = None


# ════════════════════════════════════════════════════════════════════════════
# LITERAL-PREFIX ROUTES (registered first — no collision risk)
# ════════════════════════════════════════════════════════════════════════════

@router.post("/staff/{user_id}", tags=["staff"])
def staff_start_support_session(
    user_id: int,
    request: Request,
    body: StartSupportRequest = StartSupportRequest(),
    staff: dict = Depends(require_staff_role("support")),
):
    """Staff member (role=support) initiates a 15-min support session."""
    target = _user_repo.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    if target.get("role") == "admin":
        raise HTTPException(status_code=403, detail="No se puede acceder a cuentas de administrador.")

    ip = _get_ip(request)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=SUPPORT_TTL_MINUTES)

    session_id = _support_repo.create_session(
        admin_id=staff["staff_id"],
        target_user_id=user_id,
        expires_at=expires_at,
        ip_address=ip,
        issue_description=body.issue_description,
        origin=body.origin,
        session_type="write",
        initiated_by="staff",
        staff_agent=request.headers.get("User-Agent", "")[:200],
    )

    _staff_repo.log_activity(
        staff_id=staff["staff_id"],
        action_type="support_session_start",
        description=(
            f"Sesion de soporte iniciada para {target['email']}"
            + (f" - Motivo: {body.issue_description}" if body.issue_description else "")
        ),
        target_user_id=user_id,
        ip_address=ip,
        session_id=session_id,
    )

    payload = {
        "user_id":         user_id,
        "email":           target["email"],
        "role":            target.get("role", "user"),
        "mode":            "support",
        "caller_role":     "support",
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


@router.post("/staff/{session_id}/close", tags=["staff"])
def staff_close_session(
    session_id: str,
    body: CloseSessionRequest,
    staff: dict = Depends(require_staff_role("support")),
):
    """Staff closes a support session with a result."""
    VALID_RESULTS = {"resolved", "unresolved", "escalated", "ongoing"}
    if body.result not in VALID_RESULTS:
        raise HTTPException(
            status_code=400,
            detail=f"result debe ser uno de: {', '.join(VALID_RESULTS)}",
        )

    ok = _support_repo.close_session(
        session_id=session_id,
        result=body.result,
        resolution_notes=body.resolution_notes,
        action_taken=body.action_taken,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Sesion no encontrada.")

    _staff_repo.log_activity(
        staff_id=staff["staff_id"],
        action_type="support_session_end",
        description=(
            f"Sesion cerrada: {body.result}"
            + (f" - {body.action_taken}" if body.action_taken else "")
        ),
        session_id=session_id,
    )
    return {"ok": True, "session_id": session_id, "result": body.result}


@router.get("/sessions")
def list_sessions(admin: dict = Depends(require_role("admin"))):
    """Active sessions + last 100 in history with summary stats."""
    return {
        "active":  _support_repo.get_active_sessions(),
        "history": _support_repo.get_recent_sessions(limit=100),
        "summary": _support_repo.get_sessions_summary(days=30),
    }


@router.get("/sessions/{session_id}")
def get_session_detail(
    session_id: str,
    admin: dict = Depends(require_role("admin")),
):
    """Full session detail: context, activity timeline, result."""
    session = _support_repo.get_session_detail(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sesion no encontrada.")
    activities = _support_repo.get_session_activities(session_id)

    duration_seconds = None
    if session.get("ended_at") and session.get("created_at"):
        try:
            started = datetime.fromisoformat(session["created_at"])
            ended   = datetime.fromisoformat(session["ended_at"])
            duration_seconds = int((ended - started).total_seconds())
        except Exception:
            pass

    return {
        "session":          session,
        "activities":       activities,
        "duration_seconds": duration_seconds,
        "activity_count":   len(activities),
    }


# ════════════════════════════════════════════════════════════════════════════
# PARAMETERIZED ROUTES (registered last to avoid literal-prefix collisions)
# ════════════════════════════════════════════════════════════════════════════

@router.post("/{user_id}")
def start_support_session(
    user_id: int,
    request: Request,
    body: StartSupportRequest = StartSupportRequest(),
    admin: dict = Depends(require_role("admin")),
):
    """Admin initiates a 15-min support session for the given user."""
    target = _user_repo.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    if target.get("role") == "admin":
        raise HTTPException(status_code=403, detail="No se puede impersonar a otro administrador.")

    ip = _get_ip(request)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=SUPPORT_TTL_MINUTES)
    session_id = _support_repo.create_session(
        admin_id=admin["user_id"],
        target_user_id=user_id,
        expires_at=expires_at,
        ip_address=ip,
        issue_description=body.issue_description,
        origin=body.origin,
        session_type="write",
        initiated_by="admin",
        staff_agent=request.headers.get("User-Agent", "")[:200],
    )

    payload = {
        "user_id":         user_id,
        "email":           target["email"],
        "role":            target.get("role", "user"),
        "mode":            "support",
        "caller_role":     "admin",
        "impersonated_by": admin["user_id"],
        "admin_email":     admin["email"],
        "session_id":      session_id,
        "jti":             str(uuid.uuid4()),
        "type":            "access",
        "exp":             expires_at,
    }
    token = jwt.encode(payload, SECRET, algorithm=ALGO)

    return {
        "token":           token,
        "session_id":      session_id,
        "target_email":    target["email"],
        "expires_at":      expires_at.isoformat(),
        "expires_minutes": SUPPORT_TTL_MINUTES,
    }


@router.post("/{session_id}/close")
def close_session(
    session_id: str,
    body: CloseSessionRequest,
    admin: dict = Depends(require_role("admin")),
):
    """Mark a session as closed with a result (called by admin frontend)."""
    VALID_RESULTS = {"resolved", "unresolved", "escalated", "ongoing"}
    if body.result not in VALID_RESULTS:
        raise HTTPException(
            status_code=400,
            detail=f"result debe ser uno de: {', '.join(VALID_RESULTS)}",
        )

    ok = _support_repo.close_session(
        session_id=session_id,
        result=body.result,
        resolution_notes=body.resolution_notes,
        action_taken=body.action_taken,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Sesion no encontrada.")
    return {"ok": True, "session_id": session_id, "result": body.result}


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
            detail="Sesion no encontrada, ya revocada, o no pertenece a este admin.",
        )
    return {"ok": True, "session_id": session_id}
