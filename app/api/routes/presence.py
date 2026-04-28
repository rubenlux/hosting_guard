"""
Presence & activity routes.

POST /me/heartbeat        — frontend pings every 60s to maintain online status
GET  /activity            — client's own activity timeline (filtered, no sensitive events)
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.api.security import verify_token

logger = logging.getLogger(__name__)
router = APIRouter()

_REFRESH_TOKEN_TTL = 7 * 24 * 60 * 60  # 7 days — matches main.py


class HeartbeatBody(BaseModel):
    path: str = "/"


@router.post("/me/heartbeat")
async def heartbeat(
    request: Request,
    body: HeartbeatBody,
    user: dict = Depends(verify_token),
):
    """
    Called by the frontend every 60s.  Updates last_seen + current_path.
    Throttled: at most one DB write every 25s per session (Redis-backed).
    """
    from app.infra.audit.session_repository import upsert_session

    session_id = user.get("jti") or user.get("session_id") or str(user["user_id"])
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=_REFRESH_TOKEN_TTL)

    upsert_session(
        session_id=session_id,
        user_id=int(user["user_id"]),
        email=user.get("email", ""),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        current_path=body.path[:200],
        expires_at=expires_at,
    )
    return {"ok": True}


# Client-facing activity (own events only, no sensitive system internals)
_CLIENT_EXCLUDED_CATEGORIES = {"system", "security_internal"}
_CLIENT_EXCLUDED_TYPES = {
    "rate_limit_hit", "invalid_webhook_signature", "ownership_denied",
    "admin_impersonation_started", "admin_impersonation_ended",
}


@router.get("/activity")
def get_my_activity(
    category: Optional[str] = None,
    hosting_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(verify_token),
):
    """Client's own activity timeline — excludes sensitive internal events."""
    from app.services.activity_service import query_events

    user_id = int(user["user_id"])
    events = query_events(
        user_id=user_id,
        hosting_id=hosting_id,
        category=category if category not in _CLIENT_EXCLUDED_CATEGORIES else None,
        limit=min(limit, 100),
        offset=offset,
        exclude_system=True,
    )
    # Secondary filter for excluded event types
    visible = [e for e in events if e.get("event_type") not in _CLIENT_EXCLUDED_TYPES]
    # Mask IPs for privacy
    from app.services.activity_service import mask_ip
    for e in visible:
        e["ip"] = mask_ip(e.get("ip"))
    return {"items": visible, "total": len(visible), "offset": offset}
