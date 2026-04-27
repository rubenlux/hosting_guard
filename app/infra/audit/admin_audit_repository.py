"""Admin audit log repository."""
import logging
from typing import List, Dict, Optional
from app.infra.db import get_connection, release_connection

logger = logging.getLogger(__name__)


class AdminAuditRepository:
    def log(
        self,
        admin_id: int,
        admin_email: str,
        action: str,
        target_user_id: Optional[int] = None,
        target_email: Optional[str] = None,
        ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> None:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO admin_audit_log
                   (admin_id, admin_email, action, target_user_id, target_email,
                    ip, user_agent, details, reason, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())""",
                (admin_id, admin_email, action, target_user_id, target_email,
                 ip, user_agent, details, reason),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            logger.error("[audit] Failed to log admin action: %s", action)
        finally:
            release_connection(conn)

    def get_recent(self, limit: int = 200) -> List[Dict]:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """SELECT audit_id, admin_id, admin_email, action, target_user_id,
                          target_email, ip, details, reason, created_at
                   FROM admin_audit_log ORDER BY created_at DESC LIMIT %s""",
                (limit,),
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            release_connection(conn)

    def get_for_user(self, target_user_id: int, limit: int = 50) -> List[Dict]:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """SELECT audit_id, admin_id, admin_email, action, ip, details, created_at
                   FROM admin_audit_log WHERE target_user_id=%s
                   ORDER BY created_at DESC LIMIT %s""",
                (target_user_id, limit),
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            release_connection(conn)
