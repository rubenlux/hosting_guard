from datetime import datetime, timezone
from typing import Optional, Dict, List
import logging
from app.infra.db import get_connection, release_connection

logger = logging.getLogger(__name__)

class UserRepository:
    """Repositorio de Usuarios - Versión PostgreSQL."""

    def create_user(self, email: str, password_hash: str, role: str = "user") -> int:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (email, password_hash, role, created_at) "
                "VALUES (%s, %s, %s, %s) RETURNING user_id",
                (email, password_hash, role, datetime.now(timezone.utc).isoformat())
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

    def get_user_by_email(self, email: str) -> Optional[Dict]:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            # password_hash included — required for login credential verification only
            cursor.execute(
                "SELECT user_id, email, password_hash, role, plan, balance, "
                "has_payment_method, autoscale_enabled, created_at "
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
                "SELECT user_id, email, role, plan, balance, "
                "has_payment_method, autoscale_enabled, created_at "
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
                "SELECT user_id, email, role, plan, balance, has_payment_method, autoscale_enabled, created_at "
                "FROM users ORDER BY created_at DESC"
            )
            return [dict(row) for row in cursor.fetchall()]
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
