"""Notification repository — CRUD for the notifications table."""
import json
import logging
from typing import Optional, List, Dict

from app.infra.db import get_connection, release_connection

logger = logging.getLogger(__name__)

CRITICAL_SEVERITIES = {"critical", "security"}
CRITICAL_CATEGORIES = {"security"}

# categories that map to existing user pref keys
_CAT_TO_PREF = {
    "hosting": "site_down",
    "performance": "high_usage",
    "ssl": "ssl_expiring",
    "backup": "backup_done",
    "migration": "import_done",
    "billing": "payment",
}


class NotificationRepository:
    def create(
        self,
        user_id: int,
        title: str,
        message: str,
        category: str,
        severity: str,
        channel: str = "dashboard",
        action_url: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Optional[int]:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO notifications
                   (user_id, title, message, category, severity, channel, status,
                    action_url, metadata, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,'unread',%s,%s, NOW())
                   RETURNING notification_id""",
                (user_id, title[:200], message[:1000], category, severity, channel,
                 action_url, json.dumps(metadata) if metadata else None),
            )
            row = cur.fetchone()
            conn.commit()
            return row["notification_id"] if row else None
        except Exception:
            conn.rollback()
            raise
        finally:
            release_connection(conn)

    def bulk_create(self, user_ids: List[int], title: str, message: str,
                    category: str, severity: str, channel: str = "dashboard",
                    action_url: Optional[str] = None, metadata: Optional[dict] = None) -> int:
        if not user_ids:
            return 0
        conn = get_connection()
        try:
            cur = conn.cursor()
            meta_json = json.dumps(metadata) if metadata else None
            args = [
                (uid, title[:200], message[:1000], category, severity, channel,
                 action_url, meta_json)
                for uid in user_ids
            ]
            from psycopg2.extras import execute_values
            execute_values(
                cur,
                """INSERT INTO notifications
                   (user_id, title, message, category, severity, channel, status,
                    action_url, metadata, created_at)
                   VALUES %s""",
                [(uid, t, m, cat, sev, ch, url, meta)
                 for uid, t, m, cat, sev, ch, url, meta in args],
                template="(%s,%s,%s,%s,%s,%s,'unread',%s,%s,NOW())",
            )
            count = cur.rowcount
            conn.commit()
            return count
        except Exception:
            conn.rollback()
            raise
        finally:
            release_connection(conn)

    def get_for_user(self, user_id: int, status: Optional[str] = None,
                     category: Optional[str] = None,
                     limit: int = 30, offset: int = 0) -> List[Dict]:
        conn = get_connection()
        try:
            cur = conn.cursor()
            wheres = ["user_id = %s"]
            params: list = [user_id]
            if status and status != "all":
                wheres.append("status = %s")
                params.append(status)
            if category and category != "all":
                wheres.append("category = %s")
                params.append(category)
            params += [limit, offset]
            cur.execute(
                f"""SELECT notification_id, title, message, category, severity,
                           channel, status, action_url, metadata, created_at, read_at
                    FROM notifications WHERE {' AND '.join(wheres)}
                    ORDER BY created_at DESC LIMIT %s OFFSET %s""",
                params,
            )
            rows = cur.fetchall()
            result = []
            for row in rows:
                d = dict(row)
                if d.get("metadata") and isinstance(d["metadata"], str):
                    try:
                        d["metadata"] = json.loads(d["metadata"])
                    except Exception:
                        pass
                result.append(d)
            return result
        finally:
            release_connection(conn)

    def get_unread_count(self, user_id: int) -> int:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM notifications WHERE user_id=%s AND status='unread'",
                (user_id,),
            )
            row = cur.fetchone()
            return row["cnt"] if row else 0
        finally:
            release_connection(conn)

    def mark_read(self, notification_id: int, user_id: int) -> bool:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """UPDATE notifications SET status='read', read_at=NOW()
                   WHERE notification_id=%s AND user_id=%s AND status='unread'""",
                (notification_id, user_id),
            )
            conn.commit()
            return cur.rowcount > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            release_connection(conn)

    def mark_all_read(self, user_id: int) -> int:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """UPDATE notifications SET status='read', read_at=NOW()
                   WHERE user_id=%s AND status='unread'""",
                (user_id,),
            )
            count = cur.rowcount
            conn.commit()
            return count
        except Exception:
            conn.rollback()
            raise
        finally:
            release_connection(conn)

    def archive(self, notification_id: int, user_id: int) -> bool:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE notifications SET status='archived' WHERE notification_id=%s AND user_id=%s",
                (notification_id, user_id),
            )
            conn.commit()
            return cur.rowcount > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            release_connection(conn)

    def get_admin_history(self, limit: int = 100) -> List[Dict]:
        """Returns notifications sent by admins (has metadata.sent_by_admin)."""
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """SELECT notification_id, user_id, title, message, category, severity,
                          channel, status, created_at, metadata
                   FROM notifications
                   WHERE metadata::text LIKE '%sent_by_admin%'
                   ORDER BY created_at DESC LIMIT %s""",
                (limit,),
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            release_connection(conn)

    def get_full_log(
        self,
        limit: int = 200,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        source: Optional[str] = None,   # 'auto' | 'admin' | None=all
    ) -> List[Dict]:
        """Full notification audit log with recipient email. Admin-only."""
        conn = get_connection()
        try:
            cur = conn.cursor()
            wheres = ["1=1"]
            params: list = []
            if category:
                wheres.append("n.category = %s")
                params.append(category)
            if severity:
                wheres.append("n.severity = %s")
                params.append(severity)
            if source == "admin":
                wheres.append("n.metadata::text LIKE '%sent_by_admin%'")
            elif source == "auto":
                wheres.append("(n.metadata IS NULL OR n.metadata::text NOT LIKE '%sent_by_admin%')")
            params.append(limit)
            cur.execute(
                f"""SELECT n.notification_id, n.user_id, u.email AS user_email,
                           n.title, n.message, n.category, n.severity,
                           n.channel, n.status, n.action_url,
                           n.metadata, n.created_at, n.read_at
                    FROM notifications n
                    LEFT JOIN users u ON u.user_id = n.user_id
                    WHERE {' AND '.join(wheres)}
                    ORDER BY n.created_at DESC LIMIT %s""",
                params,
            )
            rows = cur.fetchall()
            result = []
            for row in rows:
                d = dict(row)
                if d.get("metadata") and isinstance(d["metadata"], str):
                    try:
                        import json as _json
                        d["metadata"] = _json.loads(d["metadata"])
                    except Exception:
                        pass
                result.append(d)
            return result
        finally:
            release_connection(conn)
