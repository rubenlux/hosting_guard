"""
Notification service — single entry point for all system notifications.

Usage:
    from app.services.notification_service import notify, notify_bulk
    notify(user_id=5, title="Sitio creado", message="...", category="hosting", severity="success")

Non-blocking by design: exceptions are caught and logged, never propagated.
"""
import logging
from typing import Optional, List

logger = logging.getLogger(__name__)

# Severities/categories that bypass user preferences — always delivered
_FORCED_SEVERITIES = {"critical"}
_FORCED_CATEGORIES = {"security"}
_FORCED_BILLING    = {"pagos_fallidos", "suspension"}

# Map category to user pref key (notification_prefs JSON in users table)
_PREF_KEY = {
    "account":     None,   # always on
    "security":    None,   # always on (forced)
    "hosting":     "site_down",
    "wordpress":   "import_done",
    "backup":      "backup_done",
    "migration":   "import_done",
    "domain":      None,
    "ssl":         "ssl_expiring",
    "billing":     "payment",
    "performance": "high_usage",
    "support":     None,
    "system":      None,
}


def _is_forced(severity: str, category: str) -> bool:
    return severity in _FORCED_SEVERITIES or category in _FORCED_CATEGORIES


def _user_wants(prefs: dict, category: str, severity: str) -> bool:
    if _is_forced(severity, category):
        return True
    pref_key = _PREF_KEY.get(category)
    if pref_key is None:
        return True
    return prefs.get(pref_key, True)  # default True (opt-out model)


def notify(
    user_id: int,
    title: str,
    message: str,
    category: str,
    severity: str,
    channel: str = "dashboard",
    action_url: Optional[str] = None,
    metadata: Optional[dict] = None,
    _user_email: Optional[str] = None,   # pass to avoid extra DB lookup for email
    _user_prefs: Optional[dict] = None,  # pass if already known
) -> Optional[int]:
    """
    Create a notification for a single user. Best-effort — never raises.
    Returns notification_id or None.
    """
    try:
        from app.infra.audit.notification_repository import NotificationRepository
        from app.infra.audit.user_repository import UserRepository

        _notif_repo = NotificationRepository()

        # Check user preferences (only if prefs not already passed)
        prefs = _user_prefs or {}
        if _user_prefs is None:
            try:
                _user_repo = UserRepository()
                user = _user_repo.get_user_by_id(user_id)
                prefs = (user or {}).get("notification_prefs") or {}
                if not _user_email:
                    _user_email = (user or {}).get("email")
            except Exception:
                pass

        if not _user_wants(prefs, category, severity):
            return None

        notif_id = _notif_repo.create(
            user_id=user_id,
            title=title,
            message=message,
            category=category,
            severity=severity,
            channel=channel,
            action_url=action_url,
            metadata=metadata,
        )

        # Send email if channel requires it
        if channel in ("email", "both") and _user_email:
            _send_notification_email(_user_email, title, message, severity, action_url)

        return notif_id
    except Exception as exc:
        logger.error("[notify] Failed for user %s: %s", user_id, exc)
        return None


def notify_bulk(
    user_ids: List[int],
    title: str,
    message: str,
    category: str,
    severity: str,
    channel: str = "dashboard",
    action_url: Optional[str] = None,
    metadata: Optional[dict] = None,
    admin_id: Optional[int] = None,
) -> int:
    """Bulk-create notifications. Returns count created."""
    if not user_ids:
        return 0
    try:
        from app.infra.audit.notification_repository import NotificationRepository
        _notif_repo = NotificationRepository()

        meta = dict(metadata or {})
        if admin_id:
            meta["sent_by_admin"] = admin_id

        count = _notif_repo.bulk_create(
            user_ids=user_ids,
            title=title,
            message=message,
            category=category,
            severity=severity,
            channel=channel,
            action_url=action_url,
            metadata=meta,
        )
        return count
    except Exception as exc:
        logger.error("[notify_bulk] Failed: %s", exc)
        return 0


def _send_notification_email(
    to_email: str, title: str, message: str, severity: str,
    action_url: Optional[str] = None,
) -> None:
    """Best-effort email send for a notification."""
    try:
        from app.services.mailer import _send, _html_wrap, _btn, _cfg
        app_url = _cfg()["app_url"]

        severity_color = {
            "critical": "#ef4444", "warning": "#f59e0b",
            "success": "#00ff88", "security": "#f59e0b",
            "info": "#60a5fa", "billing": "#a855f7",
            "action_required": "#f59e0b",
        }.get(severity, "#60a5fa")

        action_html = ""
        if action_url:
            link = action_url if action_url.startswith("http") else f"{app_url}{action_url}"
            action_html = f'<p style="margin:24px 0 0;text-align:center;">{_btn(link, "VER DETALLES")}</p>'

        body_html = f"""
          <div style="display:inline-block;padding:4px 10px;border-radius:20px;
               background:{severity_color}22;border:1px solid {severity_color}44;
               font-size:11px;font-weight:700;color:{severity_color};
               text-transform:uppercase;letter-spacing:.05em;margin-bottom:16px;">
            {severity}
          </div>
          <h2 style="margin:0 0 12px;font-size:20px;font-weight:800;color:#fff;">{title}</h2>
          <p style="margin:0;font-size:14px;color:#aaa;line-height:1.7;">{message}</p>
          {action_html}
        """
        body_text = f"{title}\n\n{message}"
        if action_url:
            link = action_url if action_url.startswith("http") else f"{app_url}{action_url}"
            body_text += f"\n\nVer detalles: {link}"

        _send(to_email, f"{title} — HostingGuard", _html_wrap(title, body_html), body_text)
    except Exception as exc:
        logger.error("[notify_email] Failed to send to %s: %s", to_email, exc)


# ── Targeting helpers (for admin manual sends) ───────────────────────────────

def get_target_user_ids(target_type: str, target_value: Optional[str] = None) -> List[int]:
    """
    Resolve a targeting spec to a list of user_ids.
    target_type: all | user | plan | site_down | pending_payment | high_usage | migration_pending
    target_value: user_id for 'user', plan name for 'plan'
    """
    try:
        from app.infra.audit.user_repository import UserRepository
        from app.infra.audit.hosting_repository import HostingRepository
        _user_repo = UserRepository()
        _hosting_repo = HostingRepository()

        if target_type == "user":
            return [int(target_value)] if target_value else []

        if target_type == "all":
            users = _user_repo.get_all_users()
            return [u["user_id"] for u in users]

        if target_type == "plan":
            users = _user_repo.get_all_users()
            return [u["user_id"] for u in users if u.get("plan") == target_value]

        if target_type == "site_down":
            hostings = _hosting_repo.get_all_hostings()
            return list({h["user_id"] for h in hostings if h.get("status") in ("error", "zombie", "stopped")})

        if target_type == "pending_payment":
            users = _user_repo.get_all_users()
            return [u["user_id"] for u in users if (u.get("balance") or 0) < 0]

        if target_type == "high_usage":
            # users with at least one active hosting (approximate — no real-time CPU here)
            hostings = _hosting_repo.get_all_hostings()
            return list({h["user_id"] for h in hostings if h.get("status") == "active"})

        return []
    except Exception as exc:
        logger.error("[get_target_user_ids] %s", exc)
        return []
