"""
User session / presence repository.

Heartbeat throttle: uses Redis to skip DB writes when the session was
updated less than 25 seconds ago. Falls back to always writing if Redis
is unavailable.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.infra.db import get_connection, release_connection

logger = logging.getLogger(__name__)

_THROTTLE_SECONDS = 25   # minimum gap between DB writes per session
_ONLINE_SECONDS   = 120  # last_seen <= 2 min → online
_ACTIVE_SECONDS   = 900  # last_seen <= 15 min → active
_IDLE_SECONDS     = 1800 # last_seen <= 30 min → idle


def _throttle_key(session_id: str) -> str:
    return f"hb:{session_id}"


def upsert_session(
    session_id: str,
    user_id: int,
    email: str,
    ip: Optional[str],
    user_agent: Optional[str],
    current_path: Optional[str],
    expires_at: Optional[datetime],
) -> bool:
    """
    Create or update a session row. Throttled via Redis.
    Returns True if a DB write happened, False if throttled.
    """
    # Redis throttle: skip DB write if updated recently
    try:
        from app.infra.redis_client import get_redis
        r = get_redis()
        if r:
            key = _throttle_key(session_id)
            if r.exists(key):
                return False   # still within throttle window
            r.setex(key, _THROTTLE_SECONDS, "1")
    except Exception:
        pass  # Redis unavailable — proceed without throttle

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO user_sessions
               (session_id, user_id, email, ip, user_agent, current_path,
                last_seen, created_at, expires_at, is_active)
               VALUES (%s,%s,%s,%s,%s,%s,NOW(),NOW(),%s,TRUE)
               ON CONFLICT (session_id) DO UPDATE SET
                   last_seen    = NOW(),
                   current_path = EXCLUDED.current_path,
                   ip           = EXCLUDED.ip,
                   user_agent   = EXCLUDED.user_agent,
                   is_active    = TRUE""",
            (session_id, user_id, email, ip, user_agent, current_path, expires_at),
        )
        conn.commit()
        return True
    except Exception:
        logger.exception("session_repo: upsert failed for session_id=%s", session_id)
        conn.rollback()
        return False
    finally:
        release_connection(conn)


def deactivate_session(session_id: str) -> None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE user_sessions SET is_active = FALSE WHERE session_id = %s",
            (session_id,),
        )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        release_connection(conn)


def get_online_users(window_seconds: int = _ONLINE_SECONDS) -> list:
    """Return sessions active within `window_seconds`."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT s.session_id, s.user_id, s.email, s.ip, s.user_agent,
                      s.current_path, s.last_seen, s.created_at,
                      u.plan, u.role, u.subscription_status
               FROM user_sessions s
               LEFT JOIN users u USING (user_id)
               WHERE s.is_active = TRUE
                 AND s.last_seen >= NOW() - (%s || ' seconds')::INTERVAL
               ORDER BY s.last_seen DESC""",
            (str(window_seconds),),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        release_connection(conn)


def get_presence_summary() -> dict:
    """Count sessions by presence bucket."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT
                 COUNT(*) FILTER (WHERE last_seen >= NOW() - INTERVAL '2 minutes')  AS online_now,
                 COUNT(*) FILTER (WHERE last_seen >= NOW() - INTERVAL '15 minutes') AS active_15m,
                 COUNT(*) FILTER (WHERE last_seen >= NOW() - INTERVAL '30 minutes') AS idle_30m
               FROM user_sessions
               WHERE is_active = TRUE"""
        )
        row = cur.fetchone()
        return dict(row) if row else {"online_now": 0, "active_15m": 0, "idle_30m": 0}
    finally:
        release_connection(conn)


def get_all_active_sessions(limit: int = 100) -> list:
    """All sessions active in the last 30 min — for the admin table."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT s.session_id, s.user_id, s.email, s.ip, s.user_agent,
                      s.current_path, s.last_seen, s.created_at,
                      u.plan, u.role, u.subscription_status
               FROM user_sessions s
               LEFT JOIN users u USING (user_id)
               WHERE s.is_active = TRUE
                 AND s.last_seen >= NOW() - INTERVAL '30 minutes'
               ORDER BY s.last_seen DESC
               LIMIT %s""",
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        release_connection(conn)


def cleanup_sessions(inactive_days: int = 30) -> int:
    """Mark expired sessions inactive; delete rows older than inactive_days. Returns deleted count."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        # Mark expired (token TTL passed)
        cur.execute(
            "UPDATE user_sessions SET is_active = FALSE WHERE expires_at < NOW() AND is_active = TRUE"
        )
        # Hard-delete very old rows
        cur.execute(
            "DELETE FROM user_sessions WHERE created_at < NOW() - (%s || ' days')::INTERVAL",
            (str(inactive_days),),
        )
        deleted = cur.rowcount
        conn.commit()
        return deleted
    except Exception:
        conn.rollback()
        return 0
    finally:
        release_connection(conn)
