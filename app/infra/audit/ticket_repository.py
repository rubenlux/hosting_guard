import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from app.infra.db import get_connection

logger = logging.getLogger(__name__)

class TicketRepository:
    """Implementación PostgreSQL para el sistema de tickets/chat."""
    def __init__(self):
        pass

    def list_categories(self) -> List[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ticket_categories WHERE is_active = 1 ORDER BY category_id")
        return [dict(row) for row in cursor.fetchall()]

    def get_category_by_name(self, name: str) -> Optional[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ticket_categories WHERE name = %s", (name,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def create_ticket(self, user_id: int, category: str, title: str, priority: str = "medium",
                      hosting_id: Optional[int] = None, ai_summary: Optional[str] = None) -> int:
        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """INSERT INTO support_tickets
                   (user_id, hosting_id, category, status, priority, title, ai_summary, created_at, updated_at)
                   VALUES (%s,%s,%s,'open',%s,%s,%s,%s,%s) RETURNING ticket_id""",
                (user_id, hosting_id, category, priority, title, ai_summary, now, now),
            )
            row = cursor.fetchone()
            conn.commit()
            return row["ticket_id"] if row else None
        except Exception:
            conn.rollback()
            raise

    def get_ticket(self, ticket_id: int) -> Optional[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT t.*, u.email AS user_email, sa.full_name AS assigned_name, sa.email AS assigned_email
               FROM support_tickets t
               LEFT JOIN users u ON t.user_id = u.user_id
               LEFT JOIN staff_accounts sa ON t.assigned_to = sa.staff_id
               WHERE t.ticket_id = %s""",
            (ticket_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_tickets_for_user(self, user_id: int, limit: int = 20) -> List[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT t.*, sa.full_name AS assigned_name FROM support_tickets t
               LEFT JOIN staff_accounts sa ON t.assigned_to = sa.staff_id
               WHERE t.user_id = %s ORDER BY t.created_at DESC LIMIT %s""",
            (user_id, limit),
        )
        return [dict(row) for row in cursor.fetchall()]

    def list_tickets_for_staff(self, staff_id: Optional[int] = None, status: Optional[str] = None, limit: int = 50) -> List[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        conditions = []
        params: list = []
        if staff_id is not None:
            conditions.append("t.assigned_to = %s")
            params.append(staff_id)
        if status is not None:
            conditions.append("t.status = %s")
            params.append(status)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.append(limit)
        cursor.execute(
            f"""SELECT t.*, u.email AS user_email, u.plan AS user_plan, sa.full_name AS assigned_name
               FROM support_tickets t
               LEFT JOIN users u ON t.user_id = u.user_id
               LEFT JOIN staff_accounts sa ON t.assigned_to = sa.staff_id
               {where}
               ORDER BY
                 CASE t.priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END,
                 t.created_at ASC LIMIT %s""",
            params,
        )
        return [dict(row) for row in cursor.fetchall()]

    def list_queue(self, limit: int = 50) -> List[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT t.*, u.email AS user_email, u.plan AS user_plan FROM support_tickets t
               LEFT JOIN users u ON t.user_id = u.user_id
               WHERE t.status IN ('open', 'ai_handled', 'waiting')
               ORDER BY
                 CASE t.priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END,
                 t.created_at ASC LIMIT %s""",
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def update_ticket_status(self, ticket_id: int, status: str, assigned_to: Optional[int] = None,
                              ai_summary: Optional[str] = None, resolved_at: Optional[str] = None) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        cursor = conn.cursor()
        fields = ["status = %s", "updated_at = %s"]
        params: list = [status, now]
        if assigned_to is not None:
            fields.append("assigned_to = %s")
            params.append(assigned_to)
        if ai_summary is not None:
            fields.append("ai_summary = %s")
            params.append(ai_summary)
        if resolved_at is not None:
            fields.append("resolved_at = %s")
            params.append(resolved_at)
        params.append(ticket_id)
        cursor.execute(f"UPDATE support_tickets SET {', '.join(fields)} WHERE ticket_id = %s", params)
        conn.commit()
        return cursor.rowcount > 0

    def count_waiting_tickets(self) -> int:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE status IN ('open','ai_handled','waiting')")
        row = cursor.fetchone()
        return row["count"] if row else 0

    def add_message(self, ticket_id: int, sender_type: str, content: str, sender_id: Optional[int] = None, 
                    metadata: Optional[dict] = None) -> int:
        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        cursor = conn.cursor()
        meta_str = json.dumps(metadata) if metadata else None
        try:
            cursor.execute(
                """INSERT INTO ticket_messages (ticket_id, sender_type, sender_id, content, metadata, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s) RETURNING message_id""",
                (ticket_id, sender_type, sender_id, content, meta_str, now),
            )
            row = cursor.fetchone()
            msg_id = row["message_id"] if row else 0
            cursor.execute("UPDATE support_tickets SET updated_at = %s WHERE ticket_id = %s", (now, ticket_id))
            conn.commit()
            return msg_id
        except Exception:
            conn.rollback()
            raise

    def list_messages(self, ticket_id: int) -> List[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT m.*, CASE m.sender_type WHEN 'staff' THEN sa.full_name WHEN 'user' THEN u.email ELSE NULL END AS sender_name
               FROM ticket_messages m
               LEFT JOIN staff_accounts sa ON m.sender_id = sa.staff_id AND m.sender_type = 'staff'
               LEFT JOIN users u ON m.sender_id = u.user_id AND m.sender_type = 'user'
               WHERE m.ticket_id = %s ORDER BY m.created_at ASC""",
            (ticket_id,),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        for r in rows:
            if r.get("metadata"):
                try: r["metadata"] = json.loads(r["metadata"])
                except Exception: pass
        return rows
