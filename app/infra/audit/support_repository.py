import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from app.infra.db import get_connection

logger = logging.getLogger(__name__)

class SupportSessionRepository:
    """Repositorio PostgreSQL para Sesiones de Soporte."""
    def __init__(self):
        pass

    def create_session(self, admin_id: int, target_user_id: int, expires_at: datetime, ip_address: str,
                       issue_description: Optional[str] = None, origin: str = "manual",
                       session_type: str = "write", initiated_by: str = "admin",
                       staff_agent: Optional[str] = None, conn=None) -> str:
        session_id = str(uuid.uuid4())
        from app.infra.db import get_connection, release_connection
        own_conn = conn is None
        if own_conn:
            conn = get_connection()
        
        try:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc)
            cursor.execute(
                """INSERT INTO support_sessions
                   (session_id, admin_id, target_user_id, created_at, expires_at, 
                    ip_address, issue_description, origin, session_type, initiated_by, staff_agent)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (session_id, admin_id, target_user_id, now, expires_at, ip_address, 
                 issue_description, origin, session_type, initiated_by, staff_agent),
            )
            if own_conn:
                conn.commit()
            return session_id
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("Failed to save support session %s: %s", session_id, exc)
            if own_conn:
                conn.rollback()
            raise
        finally:
            if own_conn:
                release_connection(conn)

    def close_session(self, session_id: str, result: str, resolution_notes: Optional[str] = None,
                       action_taken: Optional[str] = None) -> bool:
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc)
            cursor.execute(
                "UPDATE support_sessions SET ended_at = %s, result = %s, resolution_notes = %s, action_taken = %s WHERE session_id = %s",
                (now, result, resolution_notes, action_taken, session_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            release_connection(conn)

    def revoke_session(self, session_id: str, admin_id: int) -> bool:
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc)
            cursor.execute(
                "UPDATE support_sessions SET revoked_at = %s WHERE session_id = %s AND admin_id = %s AND revoked_at IS NULL",
                (now, session_id, admin_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            release_connection(conn)

    def get_active_sessions(self) -> List[Dict]:
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()
            from datetime import datetime
            now = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                "SELECT s.*, u_target.email AS target_email FROM support_sessions s "
                "LEFT JOIN users u_target ON s.target_user_id = u_target.user_id "
                "WHERE s.revoked_at IS NULL AND s.expires_at > %s ORDER BY s.created_at DESC",
                (now,),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_connection(conn)

    def get_recent_sessions(self, limit: int = 50) -> List[Dict]:
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT 
                      s.session_id, s.admin_id, s.target_user_id, s.ip_address, s.issue_description,
                      s.origin, s.session_type, s.initiated_by, s.ended_at AS ended_at, s.result,
                      s.resolution_notes, s.action_taken, s.staff_agent,
                      s.created_at AS created_at,
                      s.expires_at AS expires_at,
                      s.revoked_at AS revoked_at,
                      u_target.email AS target_email,
                      COALESCE(sa.full_name, u_admin.email, 'Sistema') AS initiator_name,
                      COALESCE(sa.email, u_admin.email)                AS initiator_email,
                      COALESCE(sa.role, u_admin.role, 'admin')         AS initiator_role
                   FROM support_sessions s
                   LEFT JOIN users u_target ON s.target_user_id = u_target.user_id
                   LEFT JOIN users u_admin  ON s.admin_id = u_admin.user_id AND s.initiated_by = 'admin'
                   LEFT JOIN staff_accounts sa ON s.admin_id = sa.staff_id AND s.initiated_by = 'staff'
                   ORDER BY s.created_at DESC LIMIT %s""",
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_connection(conn)

    def get_session_detail(self, session_id: str) -> Optional[Dict]:
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT 
                      s.session_id, s.admin_id, s.target_user_id, s.ip_address, s.issue_description,
                      s.origin, s.session_type, s.initiated_by, s.result, s.resolution_notes,
                      s.action_taken, s.staff_agent,
                      s.created_at AS created_at,
                      s.expires_at AS expires_at,
                      s.revoked_at AS revoked_at,
                      s.ended_at AS ended_at,
                      u_target.email AS target_email, u_target.plan AS target_plan,
                      COALESCE(sa.full_name, u_admin.email, 'Sistema') AS initiator_name,
                      COALESCE(sa.email, u_admin.email)                AS initiator_email,
                      COALESCE(sa.role, 'admin')                       AS initiator_role
                   FROM support_sessions s
                   LEFT JOIN users u_target ON s.target_user_id = u_target.user_id
                   LEFT JOIN users u_admin  ON s.admin_id = u_admin.user_id AND s.initiated_by = 'admin'
                   LEFT JOIN staff_accounts sa ON s.admin_id = sa.staff_id AND s.initiated_by = 'staff'
                   WHERE s.session_id = %s""",
                (session_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            release_connection(conn)

    def get_session_activities(self, session_id: str) -> List[Dict]:
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT l.*,
                      sa.full_name AS staff_name, sa.email AS staff_email 
                   FROM staff_activity_log l 
                   LEFT JOIN staff_accounts sa ON l.staff_id = sa.staff_id 
                   WHERE l.session_id = %s 
                   ORDER BY l.created_at ASC""",
                (session_id,),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_connection(conn)

    def get_sessions_for_staff(self, staff_id: int, days: int = 30, limit: int = 50) -> List[Dict]:
        from app.infra.db import get_connection, release_connection
        since = datetime.now(timezone.utc) - timedelta(days=days)
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT s.session_id, s.admin_id, s.target_user_id, s.issue_description, s.result,
                          s.created_at AS created_at,
                          u_target.email AS target_email FROM support_sessions s 
                   LEFT JOIN users u_target ON s.target_user_id = u_target.user_id 
                   WHERE s.admin_id = %s AND s.initiated_by = 'staff' 
                   AND s.created_at >= %s 
                   ORDER BY s.created_at DESC LIMIT %s""",
                (staff_id, since, limit),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_connection(conn)

    def get_sessions_for_user(self, user_id: int, limit: int = 20) -> List[Dict]:
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT s.session_id, s.issue_description, s.result,
                          s.created_at AS created_at,
                          s.expires_at AS expires_at,
                          s.revoked_at AS revoked_at,
                          s.ended_at AS ended_at,
                          COALESCE(sa.full_name, u_admin.email, 'Sistema') AS admin_email
                   FROM support_sessions s
                   LEFT JOIN users u_admin ON s.admin_id = u_admin.user_id AND s.initiated_by = 'admin'
                   LEFT JOIN staff_accounts sa ON s.admin_id = sa.staff_id AND s.initiated_by = 'staff'
                   WHERE s.target_user_id = %s 
                   ORDER BY s.created_at DESC LIMIT %s""",
                (user_id, limit),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_connection(conn)

    def get_sessions_summary(self, days: int = 30) -> Dict:
        from app.infra.db import get_connection, release_connection
        since = datetime.now(timezone.utc) - timedelta(days=days)
        now = datetime.now(timezone.utc)
        conn = get_connection()
        try:
            cursor = conn.cursor()
            # Uso de columnas shadow para optimizar agregación
            cursor.execute(
                """SELECT COUNT(*) AS total,
                          COALESCE(SUM(CASE WHEN result = 'resolved' THEN 1 ELSE 0 END), 0) AS resolved,
                          COALESCE(SUM(CASE WHEN result = 'unresolved' THEN 1 ELSE 0 END), 0) AS unresolved,
                          COALESCE(SUM(CASE WHEN result = 'escalated' THEN 1 ELSE 0 END), 0) AS escalated,
                          COALESCE(SUM(CASE WHEN ended_at IS NULL AND expires_at > %s THEN 1 ELSE 0 END), 0) AS active
                   FROM support_sessions WHERE created_at >= %s""",
                (now, since),
            )
            row = cursor.fetchone()
            return dict(row) if row else {}
        finally:
            release_connection(conn)
