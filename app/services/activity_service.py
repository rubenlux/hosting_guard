"""
Unified activity event logger.

All platform events (auth, hosting lifecycle, backups, billing, imports,
scheduler, WordPress) write here. Non-blocking — errors are caught and logged
but never re-raised so callers are never affected.

Usage:
    from app.services.activity_service import log_event

    log_event(
        user_id=user["user_id"],
        event_type="login_success",
        category="auth",
        title="Inicio de sesión",
        ip=request.client.host,
        user_agent=request.headers.get("user-agent"),
    )
"""
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def log_event(
    *,
    user_id: Optional[int] = None,
    hosting_id: Optional[int] = None,
    actor_type: str = "user",
    actor_user_id: Optional[int] = None,
    actor_email: Optional[str] = None,
    event_type: str,
    category: str,
    severity: str = "info",
    title: str,
    message: Optional[str] = None,
    metadata: Optional[dict] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    source: Optional[str] = None,
) -> None:
    """Insert one activity event. Never raises."""
    from app.infra.db import get_connection, release_connection
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO activity_events
               (user_id, hosting_id, actor_type, actor_user_id, actor_email,
                event_type, category, severity, title, message, metadata,
                ip, user_agent, source)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                user_id, hosting_id, actor_type, actor_user_id, actor_email,
                event_type, category, severity, title, message,
                json.dumps(metadata or {}),
                ip, user_agent, source,
            ),
        )
        conn.commit()
    except Exception:
        logger.exception(
            "activity_service: failed to log event_type=%s user_id=%s", event_type, user_id
        )
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
    finally:
        if conn:
            release_connection(conn)


def query_events(
    user_id: Optional[int] = None,
    hosting_id: Optional[int] = None,
    category: Optional[str] = None,
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    source: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    exclude_system: bool = False,
) -> list:
    """Flexible query for activity events. Returns list of dicts."""
    from app.infra.db import get_connection, release_connection
    conn = get_connection()
    try:
        clauses: list[str] = []
        params: list = []

        if user_id is not None:
            clauses.append("user_id = %s"); params.append(user_id)
        if hosting_id is not None:
            clauses.append("hosting_id = %s"); params.append(hosting_id)
        if category:
            clauses.append("category = %s"); params.append(category)
        if event_type:
            clauses.append("event_type = %s"); params.append(event_type)
        if severity:
            clauses.append("severity = %s"); params.append(severity)
        if source:
            clauses.append("source = %s"); params.append(source)
        if date_from:
            clauses.append("created_at >= %s"); params.append(date_from)
        if date_to:
            clauses.append("created_at <= %s"); params.append(date_to)
        if exclude_system:
            clauses.append("actor_type != 'system'")

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params += [limit, offset]

        cur = conn.cursor()
        cur.execute(
            f"""SELECT event_id, user_id, hosting_id, actor_type, actor_email,
                       event_type, category, severity, title, message, metadata,
                       ip, source, created_at
                FROM activity_events
                {where}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s""",
            params,
        )
        rows = cur.fetchall()
        result = []
        for r in rows:
            row = dict(r)
            if isinstance(row.get("metadata"), str):
                try:
                    row["metadata"] = json.loads(row["metadata"])
                except Exception:
                    row["metadata"] = {}
            result.append(row)
        return result
    finally:
        release_connection(conn)


def mask_ip(ip: Optional[str]) -> Optional[str]:
    """Mask last two octets of IPv4 or last 4 groups of IPv6 for display."""
    if not ip:
        return None
    parts = ip.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.xxx.xxx"
    # IPv6: mask last 4 groups
    groups = ip.split(":")
    if len(groups) >= 4:
        return ":".join(groups[:4]) + ":xxxx:xxxx:xxxx:xxxx"
    return ip
