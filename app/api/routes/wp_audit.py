"""
Internal WordPress → HostingGuard audit event receiver.

POST /internal/wp-audit/event

The MU-plugin on each managed WP site sends events here.
Security: HMAC-SHA256 token per hosting (derived from hosting_id + server secret).
Rate limit: 60/minute per IP.

Token derivation (must match hostingguard-audit.php):
    HMAC-SHA256(key=WP_AUDIT_SECRET, msg=f"wp-audit:{hosting_id}")
"""
import hashlib
import hmac
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.api.rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/internal", tags=["internal"])

_WP_AUDIT_SECRET = os.getenv("WP_AUDIT_SECRET", "dev-change-me-in-production")

_ALLOWED_CATEGORIES = {"wordpress", "auth", "content", "plugin", "theme", "user", "system"}
_ALLOWED_SEVERITIES = {"info", "warning", "critical"}
_MAX_TITLE_LEN = 200
_MAX_MSG_LEN   = 1000


def _expected_token(hosting_id: int) -> str:
    return hmac.new(
        _WP_AUDIT_SECRET.encode(),
        f"wp-audit:{hosting_id}".encode(),
        hashlib.sha256,
    ).hexdigest()


class WpAuditPayload(BaseModel):
    hosting_id: int
    token: str
    event_type: str
    category: str = "wordpress"
    severity: str = "info"
    title: str
    message: Optional[str] = None
    metadata: Optional[dict] = None
    wp_user: Optional[str] = None
    created_at: Optional[str] = None


@router.post("/wp-audit/event")
@limiter.limit("60/minute")
async def receive_wp_audit_event(
    request: Request,
    payload: WpAuditPayload,
):
    # 1. Verify HMAC token
    expected = _expected_token(payload.hosting_id)
    if not hmac.compare_digest(payload.token, expected):
        logger.warning(
            "wp_audit: invalid token for hosting_id=%s from %s",
            payload.hosting_id, request.client.host if request.client else "?",
        )
        raise HTTPException(status_code=403, detail="Token inválido")

    # 2. Validate hosting exists
    from app.infra.audit.hosting_repository import HostingRepository
    repo = HostingRepository()
    hosting = repo.get_hosting_any(payload.hosting_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting no encontrado")

    # 3. Sanitize inputs
    category = payload.category if payload.category in _ALLOWED_CATEGORIES else "wordpress"
    severity = payload.severity if payload.severity in _ALLOWED_SEVERITIES else "info"
    title    = payload.title[:_MAX_TITLE_LEN]
    message  = (payload.message or "")[:_MAX_MSG_LEN] or None
    meta     = payload.metadata or {}
    if payload.wp_user:
        meta["wp_user"] = str(payload.wp_user)[:100]

    # 4. Log event
    from app.services.activity_service import log_event
    log_event(
        user_id=hosting["user_id"],
        hosting_id=payload.hosting_id,
        actor_type="wordpress",
        event_type=payload.event_type[:100],
        category=category,
        severity=severity,
        title=title,
        message=message,
        metadata=meta,
        source="wp-mu-plugin",
    )
    return {"ok": True}


def get_wp_audit_token(hosting_id: int) -> str:
    """Helper used by hosting creation to return the token for the MU-plugin config."""
    return _expected_token(hosting_id)
