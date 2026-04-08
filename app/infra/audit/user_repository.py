import sqlite3
from datetime import datetime, timezone
from typing import Optional, Dict, List
from app.infra.audit.sqlite import get_connection
from app.infra.db import BACKEND

_PH = "%s" if BACKEND == "postgresql" else "?"

class UserRepository:
    def __init__(self):
        pass

    def create_user(self, email: str, password_hash: str, role: str = "user") -> int:
        conn = get_connection()
        cursor = conn.cursor()
        p = _PH
        try:
            cursor.execute(
                f"INSERT INTO users (email, password_hash, role, created_at) VALUES ({p}, {p}, {p}, {p})",
                (email, password_hash, role, datetime.now(timezone.utc).isoformat())
            )
            user_id = cursor.lastrowid
            # En PostgreSQL lastrowid no siempre está disponible tras execute simple, el adapter lo maneja pero por si acaso:
            if user_id is None and BACKEND == "postgresql":
                # Si falló la captura automática via lastval()
                cursor.execute(f"SELECT user_id FROM users WHERE email = {p}", (email,))
                row = cursor.fetchone()
                user_id = row[0] if row else None
            conn.commit()
            return user_id
        except Exception as e:
            conn.rollback()
            if isinstance(e, sqlite3.IntegrityError) or "unique" in str(e).lower() or "duplicate" in str(e).lower():
                raise ValueError("Email already exists")
            raise

    def get_user_by_email(self, email: str) -> Optional[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM users WHERE email = {_PH}", (email,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM users WHERE user_id = {_PH}", (user_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    def deduct_balance_if_sufficient(self, user_id: int, amount: float) -> bool:
        conn = get_connection()
        cursor = conn.cursor()
        p = _PH
        cursor.execute(
            f"UPDATE users SET balance = balance - {p} WHERE user_id = {p} AND balance >= {p}",
            (amount, user_id, amount)
        )
        affected = cursor.rowcount
        conn.commit()
        return affected > 0

    def update_balance(self, user_id: int, amount: float):
        conn = get_connection()
        cursor = conn.cursor()
        p = _PH
        cursor.execute(f"UPDATE users SET balance = balance + {p} WHERE user_id = {p}", (amount, user_id))
        conn.commit()

    def update_payment_method(self, user_id: int, has_method: bool):
        conn = get_connection()
        cursor = conn.cursor()
        p = _PH
        cursor.execute(f"UPDATE users SET has_payment_method = {p} WHERE user_id = {p}", (1 if has_method else 0, user_id))
        conn.commit()

    def update_autoscale(self, user_id: int, enabled: bool):
        conn = get_connection()
        cursor = conn.cursor()
        p = _PH
        cursor.execute(f"UPDATE users SET autoscale_enabled = {p} WHERE user_id = {p}", (1 if enabled else 0, user_id))
        conn.commit()

    def get_all_users(self) -> List[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        # password_hash excluido deliberadamente — endpoint admin, no exponer hashes
        cursor.execute(
            "SELECT user_id, email, role, plan, balance, has_payment_method, autoscale_enabled, created_at "
            "FROM users ORDER BY created_at DESC"
        )
        return [dict(row) for row in cursor.fetchall()]

    def log_login_attempt(self, email: str, ip: str, success: bool, detail: str = "") -> None:
        conn = get_connection()
        cursor = conn.cursor()
        p = _PH
        cursor.execute(
            f"INSERT INTO login_audit (email, ip, success, detail, created_at) VALUES ({p}, {p}, {p}, {p}, {p})",
            (email, ip, 1 if success else 0, detail, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
