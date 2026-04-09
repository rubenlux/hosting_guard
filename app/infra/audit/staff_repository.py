import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from app.infra.db import get_connection

logger = logging.getLogger(__name__)

class StaffRepository:
    """Repositorio PostgreSQL para Staff y Logs de Actividad."""
    def __init__(self):
        pass

    def create_staff(self, admin_id: int, email: str, password_hash: str, full_name: str, role: str) -> int:
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO staff_accounts (admin_id, email, password_hash, full_name, role, is_active, created_at) "
                "VALUES (%s, %s, %s, %s, %s, 1, %s) RETURNING staff_id",
                (admin_id, email, password_hash, full_name, role, datetime.now(timezone.utc).isoformat()),
            )
            row = cursor.fetchone()
            conn.commit()
            return row["staff_id"] if row else None
        except Exception as exc:
            conn.rollback()
            if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                raise ValueError("Email already exists")
            raise

    def get_staff_by_email(self, email: str) -> Optional[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM staff_accounts WHERE email = %s", (email,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_staff_by_id(self, staff_id: int) -> Optional[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM staff_accounts WHERE staff_id = %s", (staff_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_staff(self) -> List[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT staff_id, admin_id, email, full_name, role, is_active, created_at, last_login_at "
            "FROM staff_accounts ORDER BY created_at DESC"
        )
        return [dict(row) for row in cursor.fetchall()]

    def update_staff(self, staff_id: int, **fields) -> bool:
        allowed = {"role", "is_active", "full_name"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates: return False
        sets = ", ".join(f"{k} = %s" for k in updates)
        values = list(updates.values()) + [staff_id]
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"UPDATE staff_accounts SET {sets} WHERE staff_id = %s", values)
        conn.commit()
        return cursor.rowcount > 0

    def deactivate_staff(self, staff_id: int) -> bool:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE staff_accounts SET is_active = 0 WHERE staff_id = %s", (staff_id,))
        conn.commit()
        return cursor.rowcount > 0

    def update_password(self, staff_id: int, password_hash: str) -> None:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE staff_accounts SET password_hash = %s WHERE staff_id = %s", (password_hash, staff_id))
        conn.commit()

    def update_last_login(self, staff_id: int) -> None:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE staff_accounts SET last_login_at = %s WHERE staff_id = %s",
                       (datetime.now(timezone.utc).isoformat(), staff_id))
        conn.commit()

    def log_activity(self, staff_id: int, action_type: str, description: str, target_user_id: Optional[int] = None,
                     target_hosting_id: Optional[int] = None, duration_seconds: Optional[int] = None,
                     ip_address: Optional[str] = None, session_id: Optional[str] = None) -> int:
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """INSERT INTO staff_activity_log
                   (staff_id, action_type, target_user_id, target_hosting_id,
                    description, duration_seconds, ip_address, session_id, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING log_id""",
                (staff_id, action_type, target_user_id, target_hosting_id, description,
                 duration_seconds, ip_address, session_id, datetime.now(timezone.utc).isoformat()),
            )
            row = cursor.fetchone()
            conn.commit()
            return row["log_id"] if row else 0
        except Exception as exc:
            logger.error("Failed to log staff activity: %s", exc)
            conn.rollback()
            raise

    def get_activity_for_staff(self, staff_id: int, limit: int = 100) -> List[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT l.*, u.email AS target_email FROM staff_activity_log l "
            "LEFT JOIN users u ON l.target_user_id = u.user_id "
            "WHERE l.staff_id = %s ORDER BY l.created_at DESC LIMIT %s",
            (staff_id, limit),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_all_activity(self, limit: int = 500) -> List[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT l.*, s.email AS staff_email, s.full_name AS staff_name,
                      s.role AS staff_role, u.email AS target_email
               FROM staff_activity_log l
               JOIN staff_accounts s ON l.staff_id = s.staff_id
               LEFT JOIN users u ON l.target_user_id = u.user_id
               ORDER BY l.created_at DESC LIMIT %s""",
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_analytics(self, days: int = 30) -> List[Dict]:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT
                 s.staff_id, s.email, s.full_name, s.role, s.is_active, s.last_login_at,
                 COUNT(l.log_id) AS total_actions,
                 COUNT(DISTINCT l.target_user_id) AS clients_served,
                 COALESCE(SUM(l.duration_seconds), 0) AS total_seconds,
                 COUNT(CASE WHEN l.action_type = 'support_session_start' THEN 1 END) AS support_sessions,
                 COUNT(CASE WHEN l.action_type = 'file_edited' THEN 1 END) AS files_edited,
                 COUNT(CASE WHEN l.action_type = 'hosting_restarted' THEN 1 END) AS restarts,
                 COUNT(CASE WHEN l.action_type = 'issue_resolved' THEN 1 END) AS issues_resolved,
                 COUNT(CASE WHEN l.action_type = 'logs_viewed' THEN 1 END) AS logs_viewed,
                 MAX(l.created_at) AS last_activity_at
               FROM staff_accounts s
               LEFT JOIN staff_activity_log l ON s.staff_id = l.staff_id AND l.created_at >= %s
               GROUP BY s.staff_id, s.email, s.full_name, s.role, s.is_active, s.last_login_at
               ORDER BY total_actions DESC""",
            (since,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_hourly_activity(self, staff_id: int, days: int = 7) -> List[Dict]:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        conn = get_connection()
        cursor = conn.cursor()
        hour_expr = "EXTRACT(HOUR FROM created_at::timestamptz)::INTEGER"
        cursor.execute(
            f"SELECT {hour_expr} AS hour, COUNT(*) AS events FROM staff_activity_log "
            "WHERE staff_id = %s AND created_at >= %s GROUP BY hour ORDER BY hour",
            (staff_id, since),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_available_staff(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT s.staff_id, s.email, s.full_name, s.role, s.last_login_at,
                      COUNT(t.ticket_id) AS active_tickets
               FROM staff_accounts s
               LEFT JOIN support_tickets t ON s.staff_id = t.assigned_to AND t.status = 'in_progress'
               WHERE s.is_active = 1
               GROUP BY s.staff_id, s.email, s.full_name, s.role, s.last_login_at
               ORDER BY active_tickets ASC, s.last_login_at DESC"""
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_staff_ticket_load(self, staff_id: int) -> int:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE assigned_to = %s AND status = 'in_progress'", (staff_id,))
        row = cursor.fetchone()
        # RealDictCursor devuelve un dict
        return row["count"] if row else 0
