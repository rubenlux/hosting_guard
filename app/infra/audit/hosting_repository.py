import sqlite3
from datetime import datetime
from typing import List, Dict, Optional
from app.infra.audit.sqlite import get_connection

class HostingRepository:
    def __init__(self):
        pass

    def create_hosting(self, user_id: int, name: str, subdomain: str, container_name: str, plan: str) -> int:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO hostings (user_id, name, subdomain, container_name, plan, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, name, subdomain, container_name, plan, "active", datetime.utcnow().isoformat())
        )
        hosting_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return hosting_id

    def get_user_hostings(self, user_id: int) -> List[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM hostings WHERE user_id = ?", (user_id,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_hosting(self, hosting_id: int, user_id: int) -> Optional[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM hostings WHERE hosting_id = ? AND user_id = ?", (hosting_id, user_id))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def delete_hosting(self, hosting_id: int, user_id: int):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM hostings WHERE hosting_id = ? AND user_id = ?", (hosting_id, user_id))
        conn.commit()
        conn.close()

    def get_hosting_by_container(self, container_name: str) -> Optional[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM hostings WHERE container_name = ?", (container_name,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def log_orchestrator_event(self, container_name: str, user_id: int, event_type: str, message: str):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO orchestrator_events (container_name, user_id, event_type, message, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (container_name, user_id, event_type, message, datetime.utcnow().isoformat())
        )
        conn.commit()
        conn.close()

    def get_orchestrator_events(self, user_id: int, limit: int = 20) -> List[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM orchestrator_events 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT ?
            """,
            (user_id, limit)
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_expiring_free_hostings(self) -> List[Dict]:
        """Retorna hostings free activos para verificar expiración."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM hostings 
            WHERE plan = 'free' AND status = 'active'
            """
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def update_hosting_status(self, hosting_id: int, status: str):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE hostings SET status = ? WHERE hosting_id = ?",
            (status, hosting_id)
        )
        conn.commit()
        conn.close()

    def get_all_user_hostings_by_user(self, user_id: int) -> List[Dict]:
        """Incluye días restantes para plan free."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM hostings WHERE user_id = ?", (user_id,))
        rows = cursor.fetchall()
        conn.close()
        result = []
        for row in rows:
            h = dict(row)
            if h["plan"] == "free":
                created = datetime.fromisoformat(h["created_at"])
                elapsed = (datetime.utcnow() - created).days
                h["days_remaining"] = max(0, 14 - elapsed)
                h["expires_in_days"] = h["days_remaining"]
            else:
                h["days_remaining"] = None
                h["expires_in_days"] = None
            result.append(h)
        return result

