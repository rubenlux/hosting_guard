import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.infra.audit.sqlite import get_connection


class SupportSessionRepository:
    """Append-only audit log of admin impersonation sessions."""

    def create_session(
        self,
        admin_id: int,
        target_user_id: int,
        expires_at: datetime,
        ip_address: str,
    ) -> str:
        session_id = str(uuid.uuid4())
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO support_sessions
               (session_id, admin_id, target_user_id, created_at, expires_at, ip_address)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                admin_id,
                target_user_id,
                datetime.now(timezone.utc).isoformat(),
                expires_at.isoformat(),
                ip_address,
            ),
        )
        conn.commit()
        return session_id

    def revoke_session(self, session_id: str, admin_id: int) -> bool:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE support_sessions SET revoked_at = ?
               WHERE session_id = ? AND admin_id = ? AND revoked_at IS NULL""",
            (datetime.now(timezone.utc).isoformat(), session_id, admin_id),
        )
        conn.commit()
        return cursor.rowcount > 0

    def get_active_sessions(self) -> List[Dict]:
        """Sessions not yet expired and not revoked."""
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """SELECT s.*, u_admin.email AS admin_email, u_target.email AS target_email
               FROM support_sessions s
               JOIN users u_admin  ON s.admin_id       = u_admin.user_id
               JOIN users u_target ON s.target_user_id = u_target.user_id
               WHERE s.revoked_at IS NULL AND s.expires_at > ?
               ORDER BY s.created_at DESC""",
            (now,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_recent_sessions(self, limit: int = 50) -> List[Dict]:
        """Full history — active + expired + revoked."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT s.*, u_admin.email AS admin_email, u_target.email AS target_email
               FROM support_sessions s
               JOIN users u_admin  ON s.admin_id       = u_admin.user_id
               JOIN users u_target ON s.target_user_id = u_target.user_id
               ORDER BY s.created_at DESC LIMIT ?""",
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_sessions_for_user(self, user_id: int, limit: int = 20) -> List[Dict]:
        """History of sessions targeting a specific user (shown to the client)."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT s.session_id, s.created_at, s.expires_at, s.revoked_at,
                      u_admin.email AS admin_email
               FROM support_sessions s
               JOIN users u_admin ON s.admin_id = u_admin.user_id
               WHERE s.target_user_id = ?
               ORDER BY s.created_at DESC LIMIT ?""",
            (user_id, limit),
        )
        return [dict(row) for row in cursor.fetchall()]
