import sqlite3
from datetime import datetime, timezone
from typing import Optional, Dict
from app.infra.audit.sqlite import get_connection

class UserRepository:
    def __init__(self):
        pass

    def create_user(self, email: str, password_hash: str, role: str = "user") -> int:
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO users (email, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                (email, password_hash, role, datetime.now(timezone.utc).isoformat())
            )
            user_id = cursor.lastrowid
            conn.commit()
            return user_id
        except sqlite3.IntegrityError:
            raise ValueError("Email already exists")

    def get_user_by_email(self, email: str) -> Optional[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    def deduct_balance_if_sufficient(self, user_id: int, amount: float) -> bool:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET balance = balance - ? WHERE user_id = ? AND balance >= ?",
            (amount, user_id, amount)
        )
        affected = cursor.rowcount
        conn.commit()
        return affected > 0

    def update_balance(self, user_id: int, amount: float):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()

    def update_payment_method(self, user_id: int, has_method: bool):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET has_payment_method = ? WHERE user_id = ?", (1 if has_method else 0, user_id))
        conn.commit()

    def update_autoscale(self, user_id: int, enabled: bool):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET autoscale_enabled = ? WHERE user_id = ?", (1 if enabled else 0, user_id))
        conn.commit()

    def log_login_attempt(self, email: str, ip: str, success: bool, detail: str = "") -> None:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO login_audit (email, ip, success, detail, created_at) VALUES (?, ?, ?, ?, ?)",
            (email, ip, 1 if success else 0, detail, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
