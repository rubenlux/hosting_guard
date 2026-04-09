from datetime import datetime, timezone
from typing import List, Dict, Optional
import logging
from app.infra.db import get_connection, release_connection, SQL_MINUTES_SINCE_CREATED, SQL_DAYS_REMAINING_14

logger = logging.getLogger(__name__)

VALID_STATUSES = {"active", "stopped", "expired", "error", "starting", "expiring"}

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
            cursor.execute("DELETE FROM hostings WHERE hosting_id = %s AND user_id = %s", (hosting_id, user_id))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            release_connection(conn)

    def admin_delete_hosting(self, hosting_id: int) -> bool:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM hostings WHERE hosting_id = %s", (hosting_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            release_connection(conn)

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
            cursor.execute("SELECT * FROM hostings WHERE plan = 'free' AND status = 'active' LIMIT %s OFFSET %s", (batch_size, offset))
            return [dict(row) for row in cursor.fetchall()]
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
            cursor.execute(
                f"SELECT *, CASE WHEN plan = 'free' THEN {SQL_DAYS_REMAINING_14} ELSE NULL END AS days_remaining "
                "FROM hostings WHERE user_id = %s LIMIT %s OFFSET %s",
                (user_id, limit, skip)
            )
            result = []
            for row in cursor.fetchall():
                h = dict(row)
                h["expires_in_days"] = h.pop("days_remaining", None)
                result.append(h)
            return result
        finally:
            release_connection(conn)
