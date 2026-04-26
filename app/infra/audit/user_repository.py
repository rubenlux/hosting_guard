from datetime import datetime, timezone
from typing import Optional, Dict, List
import logging
from app.infra.db import get_connection, release_connection

logger = logging.getLogger(__name__)

class UserRepository:
    """Repositorio de Usuarios - Versión PostgreSQL."""

    def create_user(
        self,
        email: str,
        password_hash: str,
        role: str = "user",
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> int:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users "
                "(email, password_hash, role, first_name, last_name, phone, email_verified, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, 0, %s) RETURNING user_id",
                (email, password_hash, role, first_name, last_name, phone,
                 datetime.now(timezone.utc).isoformat())
            )
            row = cursor.fetchone()
            conn.commit()
            return row["user_id"] if row else None
        except Exception as e:
            conn.rollback()
            if "unique" in str(e).lower() or "duplicate" in str(e).lower():
                raise ValueError("Email already exists")
            raise
        finally:
            release_connection(conn)

    def set_email_verified(self, user_id: int) -> None:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET email_verified = 1 WHERE user_id = %s",
                (user_id,),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            release_connection(conn)

    def update_password(self, user_id: int, new_hash: str) -> None:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET password_hash = %s WHERE user_id = %s",
                (new_hash, user_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            release_connection(conn)

    def get_user_by_email(self, email: str) -> Optional[Dict]:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            # password_hash included — required for login credential verification only
            cursor.execute(
                "SELECT user_id, email, password_hash, role, plan, plan_expires_at, "
                "first_name, last_name, phone, email_verified, "
                "balance, has_payment_method, autoscale_enabled, created_at "
                "FROM users WHERE email = %s",
                (email,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            release_connection(conn)

    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            # password_hash intentionally excluded — not needed for identity resolution
            cursor.execute(
                "SELECT user_id, email, role, plan, plan_expires_at, first_name, last_name, phone, "
                "balance, has_payment_method, autoscale_enabled, created_at "
                "FROM users WHERE user_id = %s",
                (user_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            release_connection(conn)

    def deduct_balance_if_sufficient(self, user_id: int, amount: float) -> bool:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET balance = balance - %s WHERE user_id = %s AND balance >= %s",
                (amount, user_id, amount)
            )
            affected = cursor.rowcount
            conn.commit()
            return affected > 0
        finally:
            release_connection(conn)

    def update_balance(self, user_id: int, amount: float):
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET balance = balance + %s WHERE user_id = %s", (amount, user_id))
            conn.commit()
        finally:
            release_connection(conn)

    def update_payment_method(self, user_id: int, has_method: bool):
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET has_payment_method = %s WHERE user_id = %s", (1 if has_method else 0, user_id))
            conn.commit()
        finally:
            release_connection(conn)

    def update_autoscale(self, user_id: int, enabled: bool):
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET autoscale_enabled = %s WHERE user_id = %s", (1 if enabled else 0, user_id))
            conn.commit()
        finally:
            release_connection(conn)

    def get_all_users(self) -> List[Dict]:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT user_id, email, role, plan, plan_expires_at, balance, "
                "has_payment_method, autoscale_enabled, created_at "
                "FROM users ORDER BY created_at DESC"
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_connection(conn)

    def update_plan(self, user_id: int, plan: str, plan_expires_at: Optional[str] = None) -> bool:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET plan = %s, plan_expires_at = %s WHERE user_id = %s",
                (plan, plan_expires_at, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            release_connection(conn)

    def delete_user(self, user_id: int) -> bool:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            # Remove all FK-referencing rows before deleting the user.
            # hostings should already be gone (admin_delete_hosting called upstream),
            # but we delete any remaining rows as a safety net against FK violations.
            # Delete in FK-safe order (children before parents)
            cursor.execute("DELETE FROM import_jobs WHERE user_id = %s", (user_id,))
            cursor.execute("DELETE FROM site_alerts WHERE user_id = %s", (user_id,))
            cursor.execute("DELETE FROM orchestrator_events WHERE user_id = %s", (user_id,))
            cursor.execute("DELETE FROM support_sessions WHERE admin_id = %s OR target_user_id = %s", (user_id, user_id))
            cursor.execute("DELETE FROM auth_tokens WHERE user_id = %s", (user_id,))
            cursor.execute("DELETE FROM hostings WHERE user_id = %s", (user_id,))
            cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            release_connection(conn)

    def log_login_attempt(self, email: str, ip: str, success: bool, detail: str = "") -> None:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO login_audit (email, ip, success, detail, created_at) VALUES (%s, %s, %s, %s, %s)",
                (email, ip, 1 if success else 0, detail, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
        finally:
            release_connection(conn)
