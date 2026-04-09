from datetime import datetime, timezone
from typing import Optional, Dict, List
import logging
from app.infra.audit.sqlite import get_connection

logger = logging.getLogger(__name__)

class UserRepository:
    """Repositorio de Usuarios - Versión PostgreSQL."""
    def __init__(self):
        pass

    def create_user(self, email: str, password_hash: str, role: str = "user") -> int:
        conn = get_connection()
        cursor = conn.cursor()
        try:
            # Usamos RETURNING para obtener el ID de forma atómica en Postgres
            cursor.execute(
                "INSERT INTO users (email, password_hash, role, created_at) "
                "VALUES (%s, %s, %s, %s) RETURNING user_id",
                (email, password_hash, role, datetime.now(timezone.utc).isoformat())
            )
            row = cursor.fetchone()
            user_id = row[0] if row else None # Depende del cursor factory, pero row[0] suele ser seguro en fetchone
            conn.commit()
            return user_id
        except Exception as e:
            conn.rollback()
            if "unique" in str(e).lower() or "duplicate" in str(e).lower():
                raise ValueError("Email already exists")
            raise

    def get_user_by_email(self, email: str) -> Optional[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def deduct_balance_if_sufficient(self, user_id: int, amount: float) -> bool:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET balance = balance - %s WHERE user_id = %s AND balance >= %s",
            (amount, user_id, amount)
        )
        affected = cursor.rowcount
        conn.commit()
        return affected > 0

    def update_balance(self, user_id: int, amount: float):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET balance = balance + %s WHERE user_id = %s", (amount, user_id))
        conn.commit()

    def update_payment_method(self, user_id: int, has_method: bool):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET has_payment_method = %s WHERE user_id = %s", (1 if has_method else 0, user_id))
        conn.commit()

    def update_autoscale(self, user_id: int, enabled: bool):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET autoscale_enabled = %s WHERE user_id = %s", (1 if enabled else 0, user_id))
        conn.commit()

    def get_all_users(self) -> List[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, email, role, plan, balance, has_payment_method, autoscale_enabled, created_at "
            "FROM users ORDER BY created_at DESC"
        )
        return [dict(row) for row in cursor.fetchall()]

    def log_login_attempt(self, email: str, ip: str, success: bool, detail: str = "") -> None:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO login_audit (email, ip, success, detail, created_at) VALUES (%s, %s, %s, %s, %s)",
            (email, ip, 1 if success else 0, detail, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
