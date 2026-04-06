import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.infra.audit.sqlite import get_connection

logger = logging.getLogger(__name__)


class SupportSessionRepository:
    """Append-only audit log of admin/staff impersonation sessions."""

    def create_session(
        self,
        admin_id: int,
        target_user_id: int,
        expires_at: datetime,
        ip_address: str,
        issue_description: Optional[str] = None,
        origin: str = "manual",
        session_type: str = "write",
        initiated_by: str = "admin",
        staff_agent: Optional[str] = None,
    ) -> str:
        session_id = str(uuid.uuid4())
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """INSERT INTO support_sessions
                   (session_id, admin_id, target_user_id, created_at, expires_at,
                    ip_address, issue_description, origin, session_type, initiated_by, staff_agent)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    admin_id,
                    target_user_id,
                    datetime.now(timezone.utc).isoformat(),
                    expires_at.isoformat(),
                    ip_address,
                    issue_description,
                    origin,
                    session_type,
                    initiated_by,
                    staff_agent,
                ),
            )
            conn.commit()
            logger.info(
                "Support session created: %s (admin=%s → user=%s, issue=%r)",
                session_id, admin_id, target_user_id, issue_description,
            )
        except Exception as exc:
            logger.error("Failed to save support session %s: %s", session_id, exc)
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        return session_id

    def close_session(
        self,
        session_id: str,
        result: str,
        resolution_notes: Optional[str] = None,
        action_taken: Optional[str] = None,
    ) -> bool:
        """
        Mark a session as closed with a result.
        result: resolved | unresolved | escalated | ongoing
        """
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE support_sessions
               SET ended_at = ?, result = ?, resolution_notes = ?, action_taken = ?
               WHERE session_id = ?""",
            (
                datetime.now(timezone.utc).isoformat(),
                result,
                resolution_notes,
                action_taken,
                session_id,
            ),
        )
        conn.commit()
        updated = cursor.rowcount > 0
        if updated:
            logger.info("Session %s closed: result=%s", session_id, result)
        return updated

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

    # ── Read queries ──────────────────────────────────────────────────────────

    def get_active_sessions(self) -> List[Dict]:
        """Sessions not yet expired and not revoked."""
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """SELECT s.*, u_target.email AS target_email
               FROM support_sessions s
               LEFT JOIN users u_target ON s.target_user_id = u_target.user_id
               WHERE s.revoked_at IS NULL AND s.expires_at > ?
               ORDER BY s.created_at DESC""",
            (now,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_recent_sessions(self, limit: int = 50) -> List[Dict]:
        """Full history — active + expired + revoked, enriched with initiator name."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT s.*,
                      u_target.email AS target_email,
                      COALESCE(sa.full_name, u_admin.email, 'Sistema') AS initiator_name,
                      COALESCE(sa.email, u_admin.email)                AS initiator_email,
                      COALESCE(sa.role, u_admin.role, 'admin')         AS initiator_role
               FROM support_sessions s
               LEFT JOIN users u_target ON s.target_user_id = u_target.user_id
               LEFT JOIN users u_admin  ON s.admin_id = u_admin.user_id
                                       AND s.initiated_by = 'admin'
               LEFT JOIN staff_accounts sa ON s.admin_id = sa.staff_id
                                           AND s.initiated_by = 'staff'
               ORDER BY s.created_at DESC LIMIT ?""",
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_session_detail(self, session_id: str) -> Optional[Dict]:
        """Full session detail with initiator info."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT s.*,
                      u_target.email AS target_email,
                      u_target.plan  AS target_plan,
                      COALESCE(sa.full_name, u_admin.email, 'Sistema') AS initiator_name,
                      COALESCE(sa.email, u_admin.email)                AS initiator_email,
                      COALESCE(sa.role, 'admin')                       AS initiator_role
               FROM support_sessions s
               LEFT JOIN users u_target ON s.target_user_id = u_target.user_id
               LEFT JOIN users u_admin  ON s.admin_id = u_admin.user_id
                                       AND s.initiated_by = 'admin'
               LEFT JOIN staff_accounts sa ON s.admin_id = sa.staff_id
                                           AND s.initiated_by = 'staff'
               WHERE s.session_id = ?""",
            (session_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_session_activities(self, session_id: str) -> List[Dict]:
        """All staff_activity_log entries linked to this session."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT l.*, sa.full_name AS staff_name, sa.email AS staff_email
               FROM staff_activity_log l
               LEFT JOIN staff_accounts sa ON l.staff_id = sa.staff_id
               WHERE l.session_id = ?
               ORDER BY l.created_at ASC""",
            (session_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_sessions_for_staff(self, staff_id: int, days: int = 30, limit: int = 50) -> List[Dict]:
        """Sessions initiated by a specific staff member."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT s.*, u_target.email AS target_email
               FROM support_sessions s
               LEFT JOIN users u_target ON s.target_user_id = u_target.user_id
               WHERE s.admin_id = ? AND s.initiated_by = 'staff'
                 AND s.created_at >= datetime('now', ? || ' days')
               ORDER BY s.created_at DESC LIMIT ?""",
            (staff_id, f"-{days}", limit),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_sessions_for_user(self, user_id: int, limit: int = 20) -> List[Dict]:
        """History of sessions targeting a specific user (shown to the client)."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT s.session_id, s.created_at, s.expires_at, s.revoked_at,
                      s.issue_description, s.result, s.ended_at,
                      COALESCE(sa.full_name, u_admin.email, 'Sistema') AS admin_email
               FROM support_sessions s
               LEFT JOIN users u_admin  ON s.admin_id = u_admin.user_id
                                       AND s.initiated_by = 'admin'
               LEFT JOIN staff_accounts sa ON s.admin_id = sa.staff_id
                                           AND s.initiated_by = 'staff'
               WHERE s.target_user_id = ?
               ORDER BY s.created_at DESC LIMIT ?""",
            (user_id, limit),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_sessions_summary(self, days: int = 30) -> Dict:
        """Aggregate stats for the analytics dashboard."""
        conn = get_connection()
        cursor = conn.cursor()
        since = f"-{days} days"
        cursor.execute(
            """SELECT
                 COUNT(*) AS total,
                 SUM(CASE WHEN result = 'resolved' THEN 1 ELSE 0 END) AS resolved,
                 SUM(CASE WHEN result = 'unresolved' THEN 1 ELSE 0 END) AS unresolved,
                 SUM(CASE WHEN result = 'escalated' THEN 1 ELSE 0 END) AS escalated,
                 SUM(CASE WHEN ended_at IS NULL AND expires_at > datetime('now') THEN 1 ELSE 0 END) AS active,
                 AVG(CASE
                   WHEN ended_at IS NOT NULL
                   THEN (julianday(ended_at) - julianday(created_at)) * 86400
                 END) AS avg_duration_seconds
               FROM support_sessions
               WHERE created_at >= datetime('now', ?)""",
            (since,),
        )
        row = cursor.fetchone()
        return dict(row) if row else {}
