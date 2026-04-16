import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict
from app.infra.db import get_connection, release_connection

logger = logging.getLogger(__name__)


class AuthTokenRepository:
    """
    Single-use, time-limited tokens for:
      - email_verification  (24 h)
      - password_reset      (1 h)
    """

    def create_token(
        self,
        user_id: int,
        token_type: str,        # "email_verification" | "password_reset"
        expires_minutes: int,
    ) -> str:
        token_id   = str(uuid.uuid4())
        now        = datetime.now(timezone.utc)
        expires_at = (now + timedelta(minutes=expires_minutes)).isoformat()

        conn = get_connection()
        try:
            cursor = conn.cursor()
            # Invalidate any previous unused tokens of the same type for this user
            cursor.execute(
                """UPDATE auth_tokens
                   SET used_at = %s
                   WHERE user_id = %s AND token_type = %s AND used_at IS NULL""",
                (now.isoformat(), user_id, token_type),
            )
            cursor.execute(
                """INSERT INTO auth_tokens (token_id, user_id, token_type, expires_at, created_at)
                   VALUES (%s, %s, %s, %s, %s)""",
                (token_id, user_id, token_type, expires_at, now.isoformat()),
            )
            conn.commit()
            return token_id
        except Exception:
            conn.rollback()
            raise
        finally:
            release_connection(conn)

    def get_valid_token(self, token_id: str, token_type: str) -> Optional[Dict]:
        """Returns token record only if it exists, matches type, is unused, and not expired."""
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM auth_tokens
                   WHERE token_id = %s AND token_type = %s AND used_at IS NULL""",
                (token_id, token_type),
            )
            row = cursor.fetchone()
            if not row:
                return None
            token = dict(row)

            # Check expiry
            exp_str = token["expires_at"].replace("Z", "+00:00")
            exp_dt  = datetime.fromisoformat(exp_str)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if exp_dt < datetime.now(timezone.utc):
                return None         # expired but not yet garbage-collected

            return token
        finally:
            release_connection(conn)

    def mark_used(self, token_id: str) -> None:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE auth_tokens SET used_at = %s WHERE token_id = %s",
                (datetime.now(timezone.utc).isoformat(), token_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            release_connection(conn)

    def delete_expired(self) -> int:
        """Garbage-collect tokens older than 7 days. Returns count removed."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM auth_tokens WHERE created_at < %s",
                (cutoff,),
            )
            count = cursor.rowcount
            conn.commit()
            return count
        except Exception:
            conn.rollback()
            raise
        finally:
            release_connection(conn)
