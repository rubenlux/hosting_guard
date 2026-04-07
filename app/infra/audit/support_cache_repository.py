"""
Repositorio para el cache inteligente del chat de soporte.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

from app.infra.audit.sqlite import get_connection
from app.infra.db import BACKEND

logger = logging.getLogger(__name__)

_PH = "%s" if BACKEND == "postgresql" else "?"

class SupportCacheRepository:

    def get_best_match(
        self, 
        category: str, 
        sub_intent: str, 
        hosting_id: Optional[int] = None
    ) -> Optional[Dict]:
        """
        Busca la mejor respuesta cacheada para una categoría e intención.
        Filtra por expiración y ordena por score desc.
        """
        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        cursor = conn.cursor()
        p = _PH

        query = f"""
            SELECT * FROM support_chat_cache
            WHERE category = {p} 
              AND sub_intent = {p}
              AND expires_at > {p}
        """
        params = [category, sub_intent, now]

        if hosting_id:
            # Si tenemos hosting_id, priorizamos entradas para ese hosting_id
            # o que no tengan hosting_id (generales)
            query += f" AND (hosting_id IS NULL OR hosting_id = {p})"
            params.append(hosting_id)
        else:
            query += " AND hosting_id IS NULL"

        query += " ORDER BY score DESC, uses DESC LIMIT 1"

        cursor.execute(query, params)
        row = cursor.fetchone()
        return dict(row) if row else None

    def save_cache(
        self,
        category: str,
        sub_intent: str,
        problem_summary: str,
        ai_response: str,
        ttl_minutes: int = 60,
        hosting_id: Optional[int] = None,
        hosting_status: Optional[str] = None,
        hosting_updated_at: Optional[str] = None,
    ) -> int:
        now = datetime.now(timezone.utc)
        expires = (now + timedelta(minutes=ttl_minutes)).isoformat()
        now_str = now.isoformat()
        
        conn = get_connection()
        cursor = conn.cursor()
        p = _PH
        
        try:
            cursor.execute(
                f"""INSERT INTO support_chat_cache
                   (category, sub_intent, problem_summary, ai_response, 
                    hosting_id, hosting_status_when_cached, hosting_updated_at_when_cached,
                    created_at, expires_at)
                   VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p})""",
                (category, sub_intent, problem_summary, ai_response, 
                 hosting_id, hosting_status, hosting_updated_at,
                 now_str, expires),
            )
            cache_id = cursor.lastrowid
            if cache_id is None and BACKEND == "postgresql":
                # Fallback para obtener el ID en Postgres si no lo devuelve
                cursor.execute("SELECT lastval()")
                row = cursor.fetchone()
                cache_id = row[0] if row else None
            conn.commit()
            return cache_id
        except Exception:
            conn.rollback()
            raise

    def increment_use(self, cache_id: int):
        conn = get_connection()
        cursor = conn.cursor()
        p = _PH
        cursor.execute(
            f"UPDATE support_chat_cache SET uses = uses + 1, score = score + 1 WHERE cache_id = {p}",
            (cache_id,)
        )
        conn.commit()

    def record_feedback(self, cache_id: int, resolved: bool):
        conn = get_connection()
        cursor = conn.cursor()
        p = _PH
        score_diff = 10 if resolved else -20
        res_diff = 1 if resolved else 0
        cursor.execute(
            f"""UPDATE support_chat_cache 
               SET resolutions = resolutions + {p}, 
                   score = score + {p} 
               WHERE cache_id = {p}""",
            (res_diff, score_diff, cache_id)
        )
        conn.commit()

    def invalidate_by_hosting(self, hosting_id: int, category: Optional[str] = None):
        """Invalida cache cuando el hosting cambia (ej: de caído a activo)"""
        conn = get_connection()
        cursor = conn.cursor()
        p = _PH
        where = "WHERE hosting_id = " + p
        params = [hosting_id]
        if category:
            where += " AND category = " + p
            params.append(category)
            
        cursor.execute(f"DELETE FROM support_chat_cache {where}", params)
        conn.commit()
