from datetime import datetime, timezone
from typing import List, Dict, Optional
import logging
from app.infra.db import get_connection, release_connection, SQL_MINUTES_SINCE_CREATED, SQL_DAYS_REMAINING_14

logger = logging.getLogger(__name__)

VALID_STATUSES = {"active", "stopped", "expired", "error", "starting", "expiring", "deleted", "zombie"}

class HostingRepository:
    """Implementación PostgreSQL limpia para Hostings."""

    def create_hosting(self, user_id: int, name: str, subdomain: str, container_name: str, plan: str, ip_address: Optional[str] = None) -> int:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO hostings (user_id, name, subdomain, container_name, plan, status, created_at, ip_address)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING hosting_id
                """,
                (user_id, name, subdomain, container_name, plan, "active", datetime.now(timezone.utc).isoformat(), ip_address)
            )
            row = cursor.fetchone()
            conn.commit()
            return row["hosting_id"] if row else None
        finally:
            release_connection(conn)

    def get_user_hostings(self, user_id: int) -> List[Dict]:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM hostings WHERE user_id = %s", (user_id,))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_connection(conn)

    def count_active_hostings(self, user_id: int) -> int:
        """Count non-deleted hostings for a user. Used to enforce plan container limits.

        'deleted' status means the container was explicitly removed by the user.
        'zombie' containers still occupy a slot — the user must investigate them.
        Stopped/suspended containers also count: they still hold a plan slot.
        """
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM hostings WHERE user_id = %s AND status != 'deleted'",
                (user_id,),
            )
            row = cursor.fetchone()
            return int(row["cnt"]) if row else 0
        finally:
            release_connection(conn)

    def count_active_free_users(self) -> int:
        """Count distinct users who have at least one non-deleted free hosting.

        Used to enforce the global cap (MAX_FREE_USERS) before creating a new free site.
        """
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT COUNT(DISTINCT user_id) AS cnt
                   FROM hostings
                   WHERE plan = 'free' AND status != 'deleted'"""
            )
            row = cursor.fetchone()
            return int(row["cnt"]) if row else 0
        finally:
            release_connection(conn)

    def had_free_hosting_recently(self, user_id: int, days: int = 30) -> bool:
        """Return True if this user created any free hosting in the last `days` days.

        Prevents abuse by users who delete and recreate to reset the 14-day trial.
        """
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT 1 FROM hostings
                   WHERE user_id = %s
                     AND plan = 'free'
                     AND created_at::timestamptz > NOW() - make_interval(days => %s)
                   LIMIT 1""",
                (user_id, days),
            )
            return cursor.fetchone() is not None
        finally:
            release_connection(conn)

    def get_expired_hostings(self, batch_size: int = 50, offset: int = 0) -> List[Dict]:
        """Return free hostings stuck in 'expired' state — awaiting resource cleanup."""
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM hostings WHERE status = 'expired' LIMIT %s OFFSET %s",
                (batch_size, offset),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_connection(conn)

    def count_deleted_today(self) -> int:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM hostings WHERE status = 'deleted' AND deleted_at::timestamptz > NOW() - INTERVAL '24 hours'"
            )
            row = cursor.fetchone()
            return int(row["cnt"]) if row else 0
        finally:
            release_connection(conn)

    def count_by_status(self, status: str) -> int:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) AS cnt FROM hostings WHERE status = %s", (status,))
            row = cursor.fetchone()
            return int(row["cnt"]) if row else 0
        finally:
            release_connection(conn)

    def mark_deleted(self, hosting_id: int) -> bool:
        """Soft-delete a hosting: set status='deleted' and record deleted_at timestamp.

        Never removes the row — audit trail is preserved.
        """
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE hostings SET status = 'deleted', deleted_at = %s WHERE hosting_id = %s",
                (datetime.now(timezone.utc).isoformat(), hosting_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            release_connection(conn)

    def get_hosting(self, hosting_id: int, user_id: int) -> Optional[Dict]:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM hostings WHERE hosting_id = %s AND user_id = %s", (hosting_id, user_id))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            release_connection(conn)

    def get_hosting_any(self, hosting_id: int) -> Optional[Dict]:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM hostings WHERE hosting_id = %s", (hosting_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            release_connection(conn)

    def delete_hosting(self, hosting_id: int, user_id: int) -> bool:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            self._cascade_delete(cursor, hosting_id)
            cursor.execute("DELETE FROM hostings WHERE hosting_id = %s AND user_id = %s", (hosting_id, user_id))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            release_connection(conn)

    def admin_delete_hosting(self, hosting_id: int) -> bool:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            self._cascade_delete(cursor, hosting_id)
            cursor.execute("DELETE FROM hostings WHERE hosting_id = %s", (hosting_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            release_connection(conn)

    @staticmethod
    def _cascade_delete(cursor, hosting_id: int) -> None:
        """Delete all child records that reference this hosting before deleting the parent."""
        cursor.execute("DELETE FROM site_health_history WHERE site_id = %s", (hosting_id,))
        cursor.execute("DELETE FROM site_alerts WHERE site_id = %s", (hosting_id,))
        cursor.execute("DELETE FROM ai_diagnosis WHERE hosting_id = %s", (hosting_id,))
        cursor.execute("DELETE FROM import_jobs WHERE hosting_id = %s", (hosting_id,))

    def get_hosting_by_container(self, container_name: str) -> Optional[Dict]:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM hostings WHERE container_name = %s", (container_name,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            release_connection(conn)

    def get_all_hostings(self) -> List[Dict]:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM hostings ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_connection(conn)

    def log_orchestrator_event(self, container_name: str, user_id: int, event_type: str, message: str,
                               cpu_pct: float = None, mem_pct: float = None, risk_level: str = None, simulated: bool = True):
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO orchestrator_events
                  (container_name, user_id, event_type, message, created_at,
                   cpu_pct, mem_pct, risk_level, simulated)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (container_name, user_id, event_type, message, datetime.now(timezone.utc).isoformat(),
                 cpu_pct, mem_pct, risk_level, 1 if simulated else 0),
            )
            # Limpieza automática (últimos 500 eventos por usuario)
            cursor.execute(
                """
                DELETE FROM orchestrator_events
                WHERE user_id = %s AND event_id NOT IN (
                    SELECT event_id FROM orchestrator_events
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT 500
                )
                """,
                (user_id, user_id),
            )
            conn.commit()
        finally:
            release_connection(conn)

    def get_orchestrator_events(self, user_id: int, limit: int = 20, skip: int = 0) -> List[Dict]:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM orchestrator_events WHERE user_id = %s ORDER BY created_at DESC LIMIT %s OFFSET %s",
                (user_id, limit, skip)
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_connection(conn)

    def get_all_orchestrator_events(self, limit: int = 200) -> List[Dict]:
        """Admin-only: all orchestrator events across all users, joined with user email."""
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT oe.event_id, oe.container_name, oe.user_id, oe.event_type, oe.message, oe.created_at, "
                "u.email FROM orchestrator_events oe "
                "LEFT JOIN users u ON oe.user_id = u.user_id "
                "ORDER BY oe.created_at DESC LIMIT %s",
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_connection(conn)

    def has_free_plan_from_ip(self, ip_address: str) -> bool:
        if not ip_address:
            return False
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM hostings WHERE ip_address = %s AND plan = 'free' AND status = 'active'", (ip_address,))
            row = cursor.fetchone()
            return row["count"] > 0
        finally:
            release_connection(conn)

    def get_last_event_by_type(self, container_name: str, event_type: str) -> Optional[Dict]:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM orchestrator_events WHERE container_name = %s AND event_type = %s ORDER BY created_at DESC LIMIT 1",
                (container_name, event_type)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            release_connection(conn)

    def get_stale_expiring_hostings(self, stale_minutes: int = 30) -> List[Dict]:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM hostings WHERE status = 'expiring' AND {SQL_MINUTES_SINCE_CREATED} > %s", (stale_minutes,))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_connection(conn)

    def get_expiring_free_hostings(self, batch_size: int = 100, offset: int = 0) -> List[Dict]:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT h.*, u.plan_expires_at AS user_plan_expires_at
                   FROM hostings h
                   JOIN users u ON h.user_id = u.user_id
                   WHERE h.plan = 'free' AND h.status = 'active'
                   LIMIT %s OFFSET %s""",
                (batch_size, offset),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_connection(conn)

    def update_hosting_plan(self, hosting_id: int, plan: str) -> bool:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE hostings SET plan = %s WHERE hosting_id = %s", (plan, hosting_id))
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            release_connection(conn)

    def update_hosting_status(self, hosting_id: int, status: str) -> bool:
        if status not in VALID_STATUSES:
            raise ValueError(f"Status inválido: {status}")
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE hostings SET status = %s WHERE hosting_id = %s", (status, hosting_id))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            release_connection(conn)

    def bulk_update_status(self, hosting_ids: List[int], status: str):
        if not hosting_ids:
            return
        if status not in VALID_STATUSES:
            raise ValueError(f"Status inválido: {status}")
        placeholders = ",".join(["%s"] * len(hosting_ids))
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE hostings SET status = %s WHERE hosting_id IN ({placeholders})", [status, *hosting_ids])
            conn.commit()
        finally:
            release_connection(conn)

    def get_all_user_hostings_by_user(self, user_id: int, limit: int = 50, skip: int = 0) -> List[Dict]:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            # expires_in_days priority:
            #   1. plan_expires_at LIKE '2099%'  → NULL (free forever, never show expiry)
            #   2. plan_expires_at IS NOT NULL   → days until that explicit date
            #   3. fallback                      → 14-day rule from hosting created_at
            cursor.execute(
                """SELECT h.*,
                      CASE
                        WHEN h.plan = 'free' AND u.plan_expires_at LIKE '2099%%'
                          THEN NULL
                        WHEN h.plan = 'free' AND u.plan_expires_at IS NOT NULL
                          THEN GREATEST(0,
                                 CEIL(EXTRACT(EPOCH FROM
                                   (u.plan_expires_at::timestamptz - NOW() AT TIME ZONE 'UTC')
                                 ) / 86400)
                               )::INTEGER
                        WHEN h.plan = 'free'
                          THEN GREATEST(0,
                                 14 - EXTRACT(DAY FROM AGE(
                                   NOW() AT TIME ZONE 'UTC', h.created_at::timestamptz
                                 ))::INTEGER
                               )
                        ELSE NULL
                      END AS days_remaining
                   FROM hostings h
                   JOIN users u ON h.user_id = u.user_id
                   WHERE h.user_id = %s
                   LIMIT %s OFFSET %s""",
                (user_id, limit, skip),
            )
            result = []
            for row in cursor.fetchall():
                h = dict(row)
                h["expires_in_days"] = h.pop("days_remaining", None)
                result.append(h)
            return result
        finally:
            release_connection(conn)

    def get_all_running(self) -> List[Dict]:
        """Returns all hostings whose status is 'running' — used by the zombie reconciler."""
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT hosting_id, container_name FROM hostings WHERE status = 'running'"
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_connection(conn)

    def update_status(self, hosting_id: int, status: str) -> None:
        """Updates the status of a single hosting."""
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE hostings SET status = %s WHERE hosting_id = %s",
                (status, hosting_id),
            )
            conn.commit()
        finally:
            release_connection(conn)
