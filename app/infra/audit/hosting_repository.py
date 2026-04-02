import sqlite3
from datetime import datetime
from typing import List, Dict, Optional
from contextlib import closing
from app.infra.audit.sqlite import get_connection

VALID_STATUSES = {"active", "stopped", "expired", "error", "starting", "expiring"}

class HostingRepository:
    def __init__(self):
        pass

    def create_hosting(self, user_id: int, name: str, subdomain: str, container_name: str, plan: str, ip_address: Optional[str] = None) -> int:
        with closing(get_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO hostings (user_id, name, subdomain, container_name, plan, status, created_at, ip_address)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, name, subdomain, container_name, plan, "active", datetime.utcnow().isoformat(), ip_address)
            )
            hosting_id = cursor.lastrowid
            conn.commit()
            return hosting_id

    def get_user_hostings(self, user_id: int) -> List[Dict]:
        with closing(get_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM hostings WHERE user_id = ?", (user_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_hosting(self, hosting_id: int, user_id: int) -> Optional[Dict]:
        with closing(get_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM hostings WHERE hosting_id = ? AND user_id = ?", (hosting_id, user_id))
            row = cursor.fetchone()
            return dict(row) if row else None

    def delete_hosting(self, hosting_id: int, user_id: int) -> bool:
        with closing(get_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM hostings WHERE hosting_id = ? AND user_id = ?", (hosting_id, user_id))
            conn.commit()
            return cursor.rowcount > 0

    def get_hosting_by_container(self, container_name: str) -> Optional[Dict]:
        with closing(get_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM hostings WHERE container_name = ?", (container_name,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def log_orchestrator_event(self, container_name: str, user_id: int, event_type: str, message: str):
        with closing(get_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO orchestrator_events (container_name, user_id, event_type, message, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (container_name, user_id, event_type, message, datetime.utcnow().isoformat())
            )
            # Conservar solo los últimos 500 eventos por usuario
            cursor.execute(
                """
                DELETE FROM orchestrator_events
                WHERE user_id = ? AND event_id NOT IN (
                    SELECT event_id FROM orchestrator_events
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT 500
                )
                """,
                (user_id, user_id)
            )
            conn.commit()

    def get_orchestrator_events(self, user_id: int, limit: int = 20, skip: int = 0) -> List[Dict]:
        with closing(get_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM orchestrator_events 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT ? OFFSET ?
                """,
                (user_id, limit, skip)
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def has_free_plan_from_ip(self, ip_address: str) -> bool:
        if not ip_address:
            return False
        with closing(get_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*) as count FROM hostings 
                WHERE ip_address = ? AND plan = 'free' AND status = 'active'
                """,
                (ip_address,)
            )
            row = cursor.fetchone()
            return row["count"] > 0

    def get_last_event_by_type(self, container_name: str, event_type: str) -> Optional[Dict]:
        with closing(get_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM orchestrator_events 
                WHERE container_name = ? AND event_type = ?
                ORDER BY created_at DESC 
                LIMIT 1
                """,
                (container_name, event_type)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_expiring_free_hostings(self, batch_size: int = 100, offset: int = 0) -> List[Dict]:
        with closing(get_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM hostings 
                WHERE plan = 'free' AND status = 'active'
                LIMIT ? OFFSET ?
                """,
                (batch_size, offset)
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def update_hosting_status(self, hosting_id: int, status: str):
        if status not in VALID_STATUSES:
            raise ValueError(f"Status inválido: {status}. Permitidos: {VALID_STATUSES}")
        with closing(get_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE hostings SET status = ? WHERE hosting_id = ?",
                (status, hosting_id)
            )
            conn.commit()

    def bulk_update_status(self, hosting_ids: List[int], status: str):
        if not hosting_ids:
            return
        if status not in VALID_STATUSES:
            raise ValueError(f"Status inválido: {status}. Permitidos: {VALID_STATUSES}")
        placeholders = ",".join("?" * len(hosting_ids))
        with closing(get_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE hostings SET status = ? WHERE hosting_id IN ({placeholders})",
                [status, *hosting_ids]
            )
            conn.commit()

    def get_all_user_hostings_by_user(self, user_id: int, limit: int = 50, skip: int = 0) -> List[Dict]:
        with closing(get_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT *,
                  CASE WHEN plan = 'free'
                    THEN MAX(0, 14 - CAST((julianday('now') - julianday(created_at)) AS INTEGER))
                    ELSE NULL
                  END AS days_remaining
                FROM hostings
                WHERE user_id = ?
                LIMIT ? OFFSET ?
                """,
                (user_id, limit, skip)
            )
            rows = cursor.fetchall()
            result = []
            for row in rows:
                h = dict(row)
                h["expires_in_days"] = h.get("days_remaining")
                result.append(h)
            return result
