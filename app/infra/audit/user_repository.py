from datetime import datetime, timezone
from typing import Optional, Dict, List
import json
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
                "balance, has_payment_method, autoscale_enabled, created_at, "
                "timezone, company, avatar_url, notification_prefs "
                "FROM users WHERE email = %s",
                (email,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            if d.get("notification_prefs"):
                try:
                    d["notification_prefs"] = json.loads(d["notification_prefs"])
                except Exception:
                    d["notification_prefs"] = None
            return d
        finally:
            release_connection(conn)

    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT user_id, email, role, plan, plan_expires_at, first_name, last_name, phone, "
                "balance, has_payment_method, autoscale_enabled, created_at, "
                "timezone, company, avatar_url, notification_prefs, "
                "mp_customer_id, mp_payment_id, mp_preference_id, subscription_status, "
                "current_period_start, current_period_end, trial_ends_at, "
                "plan_started_at, billing_interval, billing_portal_url "
                "FROM users WHERE user_id = %s",
                (user_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            if d.get("notification_prefs"):
                try:
                    d["notification_prefs"] = json.loads(d["notification_prefs"])
                except Exception:
                    d["notification_prefs"] = None
            return d
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

    def update_profile(self, user_id: int, first_name: str, last_name: str, phone: str,
                       timezone: Optional[str], company: Optional[str]) -> None:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET first_name=%s, last_name=%s, phone=%s, timezone=%s, company=%s "
                "WHERE user_id=%s",
                (first_name, last_name, phone, timezone, company, user_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            release_connection(conn)

    def update_avatar_url(self, user_id: int, avatar_url: str) -> None:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET avatar_url=%s WHERE user_id=%s", (avatar_url, user_id))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            release_connection(conn)

    def update_notification_prefs(self, user_id: int, prefs: dict) -> None:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET notification_prefs=%s WHERE user_id=%s",
                (json.dumps(prefs), user_id),
            )
            conn.commit()
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

    # ── Billing (MercadoPago) ─────────────────────────────────────────────────

    _BILLING_FIELDS = frozenset({
        "mp_customer_id", "mp_payment_id", "mp_preference_id", "mp_subscription_id",
        "subscription_status", "current_period_start", "current_period_end",
        "trial_ends_at", "plan_started_at", "billing_interval", "billing_portal_url", "plan",
    })

    def update_billing_subscription(self, user_id: int, **fields) -> None:
        to_update = {k: v for k, v in fields.items() if k in self._BILLING_FIELDS and v is not None}
        if not to_update:
            return
        cols = ", ".join(f"{k} = %s" for k in to_update)
        vals = list(to_update.values()) + [user_id]
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE users SET {cols} WHERE user_id = %s", vals)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            release_connection(conn)

    def get_user_by_payment_customer_id(self, customer_id: str) -> Optional[Dict]:
        """Busca un usuario por el ID de cliente del proveedor de pagos (mp_customer_id)."""
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT user_id, email, role, plan, mp_customer_id, mp_payment_id "
                "FROM users WHERE mp_customer_id = %s",
                (customer_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            release_connection(conn)

    def is_webhook_processed(self, event_id: str) -> bool:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM billing_webhook_events WHERE event_id = %s",
                (event_id,)
            )
            return cursor.fetchone() is not None
        finally:
            release_connection(conn)

    def mark_webhook_processed(self, event_id: str, event_name: str) -> None:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO billing_webhook_events (event_id, event_name, processed_at) "
                "VALUES (%s, %s, %s) ON CONFLICT (event_id) DO NOTHING",
                (event_id, event_name, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
        finally:
            release_connection(conn)
