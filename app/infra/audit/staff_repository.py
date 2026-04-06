"""
Repositorio para cuentas de colaboradores y su log de actividad.

staff_accounts      — cuentas de staff (append-only, soft-delete via is_active)
staff_activity_log  — registro de productividad (append-only, nunca se borra)
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from app.infra.audit.sqlite import get_connection

logger = logging.getLogger(__name__)


class StaffRepository:

    # -------------------------------------------------------------------------
    # Cuentas de staff
    # -------------------------------------------------------------------------

    def create_staff(
        self,
        admin_id: int,
        email: str,
        password_hash: str,
        full_name: str,
        role: str,
    ) -> int:
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """INSERT INTO staff_accounts
                   (admin_id, email, password_hash, full_name, role, is_active, created_at)
                   VALUES (?, ?, ?, ?, ?, 1, ?)""",
                (
                    admin_id,
                    email,
                    password_hash,
                    full_name,
                    role,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            staff_id = cursor.lastrowid
            conn.commit()
            logger.info("Staff account created: %s (role=%s, by admin=%s)", email, role, admin_id)
            return staff_id
        except Exception as exc:
            conn.rollback()
            if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                raise ValueError("Email already exists")
            raise

    def get_staff_by_email(self, email: str) -> Optional[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM staff_accounts WHERE email = ?", (email,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_staff_by_id(self, staff_id: int) -> Optional[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM staff_accounts WHERE staff_id = ?", (staff_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_staff(self) -> List[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT staff_id, admin_id, email, full_name, role, is_active,
                      created_at, last_login_at
               FROM staff_accounts ORDER BY created_at DESC"""
        )
        return [dict(row) for row in cursor.fetchall()]

    def update_staff(self, staff_id: int, **fields) -> bool:
        allowed = {"role", "is_active", "full_name"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return False
        sets = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [staff_id]
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"UPDATE staff_accounts SET {sets} WHERE staff_id = ?", values)
        conn.commit()
        return cursor.rowcount > 0

    def deactivate_staff(self, staff_id: int) -> bool:
        """Soft-delete: sets is_active=0. El historial se conserva."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE staff_accounts SET is_active = 0 WHERE staff_id = ?",
            (staff_id,),
        )
        conn.commit()
        return cursor.rowcount > 0

    def update_last_login(self, staff_id: int) -> None:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE staff_accounts SET last_login_at = ? WHERE staff_id = ?",
            (datetime.now(timezone.utc).isoformat(), staff_id),
        )
        conn.commit()

    # -------------------------------------------------------------------------
    # Log de actividad
    # -------------------------------------------------------------------------

    def log_activity(
        self,
        staff_id: int,
        action_type: str,
        description: str,
        target_user_id: Optional[int] = None,
        target_hosting_id: Optional[int] = None,
        duration_seconds: Optional[int] = None,
        ip_address: Optional[str] = None,
    ) -> int:
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """INSERT INTO staff_activity_log
                   (staff_id, action_type, target_user_id, target_hosting_id,
                    description, duration_seconds, ip_address, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    staff_id,
                    action_type,
                    target_user_id,
                    target_hosting_id,
                    description,
                    duration_seconds,
                    ip_address,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            log_id = cursor.lastrowid
            conn.commit()
            return log_id
        except Exception as exc:
            logger.error("Failed to log staff activity staff_id=%s type=%s: %s", staff_id, action_type, exc)
            try:
                conn.rollback()
            except Exception:
                pass
            raise

    def get_activity_for_staff(self, staff_id: int, limit: int = 100) -> List[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT l.*, u.email AS target_email
               FROM staff_activity_log l
               LEFT JOIN users u ON l.target_user_id = u.user_id
               WHERE l.staff_id = ?
               ORDER BY l.created_at DESC LIMIT ?""",
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
               ORDER BY l.created_at DESC LIMIT ?""",
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_analytics(self, days: int = 30) -> List[Dict]:
        """Métricas agregadas por colaborador para los últimos N días."""
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT
                 s.staff_id, s.email, s.full_name, s.role, s.is_active,
                 s.last_login_at,
                 COUNT(l.log_id)                                                      AS total_actions,
                 COUNT(DISTINCT l.target_user_id)                                     AS clients_served,
                 COALESCE(SUM(l.duration_seconds), 0)                                 AS total_seconds,
                 COUNT(CASE WHEN l.action_type = 'support_session_start'  THEN 1 END) AS support_sessions,
                 COUNT(CASE WHEN l.action_type = 'file_edited'            THEN 1 END) AS files_edited,
                 COUNT(CASE WHEN l.action_type = 'hosting_restarted'      THEN 1 END) AS restarts,
                 COUNT(CASE WHEN l.action_type = 'issue_resolved'         THEN 1 END) AS issues_resolved,
                 COUNT(CASE WHEN l.action_type = 'logs_viewed'            THEN 1 END) AS logs_viewed,
                 MAX(l.created_at)                                                    AS last_activity_at
               FROM staff_accounts s
               LEFT JOIN staff_activity_log l
                 ON s.staff_id = l.staff_id AND l.created_at >= ?
               GROUP BY s.staff_id
               ORDER BY total_actions DESC""",
            (since,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_hourly_activity(self, staff_id: int, days: int = 7) -> List[Dict]:
        """Distribución de actividad por hora del día (para gráfico de calor)."""
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        conn = get_connection()
        cursor = conn.cursor()
        # SQLite: strftime('%H', created_at)  |  PostgreSQL: EXTRACT(HOUR FROM created_at::timestamptz)
        from app.infra.db import BACKEND
        if BACKEND == "postgresql":
            hour_expr = "EXTRACT(HOUR FROM created_at::timestamptz)::INTEGER"
        else:
            hour_expr = "CAST(strftime('%H', created_at) AS INTEGER)"
        cursor.execute(
            f"""SELECT {hour_expr} AS hour, COUNT(*) AS events
                FROM staff_activity_log
                WHERE staff_id = ? AND created_at >= ?
                GROUP BY hour ORDER BY hour""",
            (staff_id, since),
        )
        return [dict(row) for row in cursor.fetchall()]
