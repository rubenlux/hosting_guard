from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from app.infra.db import get_connection, release_connection

class SupportCacheRepository:
    """Implementación PostgreSQL para el cache del chat de soporte."""

    def get_best_match(self, category: str, sub_intent: str, hosting_id: Optional[int] = None) -> Optional[Dict]:
        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        try:
            cursor = conn.cursor()
            query = "SELECT * FROM support_chat_cache WHERE category = %s AND sub_intent = %s AND expires_at::timestamptz > %s"
            params = [category, sub_intent, now]
            if hosting_id:
                query += " AND (hosting_id IS NULL OR hosting_id = %s)"
                params.append(hosting_id)
            else:
                query += " AND hosting_id IS NULL"
            query += " ORDER BY score DESC, uses DESC LIMIT 1"
            cursor.execute(query, params)
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            release_connection(conn)

    def save_cache(self, category: str, sub_intent: str, problem_summary: str, ai_response: str,
                   ttl_minutes: int = 60, hosting_id: Optional[int] = None,
                   hosting_status: Optional[str] = None, hosting_updated_at: Optional[str] = None) -> int:
        now = datetime.now(timezone.utc)
        expires = (now + timedelta(minutes=ttl_minutes)).isoformat()
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO support_chat_cache
                   (category, sub_intent, problem_summary, ai_response,
                    hosting_id, hosting_status_when_cached, hosting_updated_at_when_cached,
                    created_at, expires_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING cache_id""",
                (category, sub_intent, problem_summary, ai_response, hosting_id,
                 hosting_status, hosting_updated_at, now.isoformat(), expires),
            )
            row = cursor.fetchone()
            conn.commit()
            return row["cache_id"] if row else None
        except Exception:
            conn.rollback()
            raise
        finally:
            release_connection(conn)

    def increment_use(self, cache_id: int):
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE support_chat_cache SET uses = uses + 1, score = score + 1 WHERE cache_id = %s", (cache_id,))
            conn.commit()
        finally:
            release_connection(conn)

    def record_feedback(self, cache_id: int, resolved: bool):
        conn = get_connection()
        try:
            cursor = conn.cursor()
            score_diff = 10 if resolved else -20
            res_diff = 1 if resolved else 0
            cursor.execute(
                "UPDATE support_chat_cache SET resolutions = resolutions + %s, score = score + %s WHERE cache_id = %s",
                (res_diff, score_diff, cache_id)
            )
            conn.commit()
        finally:
            release_connection(conn)

    def invalidate_by_hosting(self, hosting_id: int, category: Optional[str] = None):
        conn = get_connection()
        try:
            cursor = conn.cursor()
            where = "WHERE hosting_id = %s"
            params = [hosting_id]
            if category:
                where += " AND category = %s"
                params.append(category)
            cursor.execute(f"DELETE FROM support_chat_cache {where}", params)
            conn.commit()
        finally:
            release_connection(conn)
