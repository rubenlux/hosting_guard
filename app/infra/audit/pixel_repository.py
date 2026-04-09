import json
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

def _site_status(last_seen_at: Optional[str]) -> str:
    if not last_seen_at: return "dead"
    try:
        last = last_seen_at if isinstance(last_seen_at, datetime) else datetime.fromisoformat(last_seen_at)
        if last.tzinfo is None: last = last.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - last
        if delta.total_seconds() < 86400: return "active"
        if delta.days < 7: return "warning"
        return "dead"
    except Exception: return "dead"

class PixelRepository:
    """Implementación PostgreSQL limpia para Analytics."""

    def create_site(self, user_id: int, name: str, domain: str = None) -> str:
        site_id = uuid.uuid4().hex[:12]
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO pixel_sites (site_id, user_id, name, domain, created_at) VALUES (%s, %s, %s, %s, %s)",
                (site_id, user_id, name, domain, datetime.now(timezone.utc))
            )
            conn.commit()
            return site_id
        except Exception:
            conn.rollback()
            raise
        finally:
            release_connection(conn)

    def get_user_sites(self, user_id: int) -> List[Dict]:
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM pixel_sites WHERE user_id = %s", (user_id,))
            rows = cursor.fetchall()
            sites = []
            for r in rows:
                d = dict(r)
                d["status"] = _site_status(d.get("last_seen_at"))
                sites.append(d)
            return sites
        finally:
            release_connection(conn)

    def get_site(self, site_id: str) -> Optional[Dict]:
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM pixel_sites WHERE site_id = %s", (site_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            release_connection(conn)

    def save_event(self, **kwargs) -> str:
        event_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()
            props = kwargs.get("properties", {})
            props_json = json.dumps(props) if isinstance(props, dict) else props

            cursor.execute(
                """INSERT INTO pixel_events
                   (event_id, site_id, user_id, event_type, url, referrer, user_agent,
                    ip, country, device, browser, os, properties, session_id, created_at,
                    visitor_id, region, city)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (event_id, kwargs.get("site_id"), kwargs.get("user_id"), kwargs.get("event_type"),
                 kwargs.get("url"), kwargs.get("referrer"), kwargs.get("user_agent"),
                 kwargs.get("ip"), kwargs.get("country"), kwargs.get("device"), kwargs.get("browser"),
                 kwargs.get("os"), props_json,
                 kwargs.get("session_id"), now, kwargs.get("visitor_id"), kwargs.get("region"), kwargs.get("city"))
            )
            cursor.execute("UPDATE pixel_sites SET last_seen_at = %s WHERE site_id = %s", (now, kwargs.get("site_id")))
            conn.commit()
            return event_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Error saving pixel event: {e}", exc_info=True)
            raise
        finally:
            release_connection(conn)

    def get_stats(self, site_id: str, days: int = 30) -> Dict:
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()
            since = datetime.now(timezone.utc) - timedelta(days=days)
            today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

            # Query 1: Métricas calientes (Dashboard Core)
            # Optimizada para no tener que scanear la tabla por el bounce_rate
            cursor.execute(
                """
                SELECT 
                    COUNT(*) as total_events,
                    COUNT(*) FILTER (WHERE created_at >= %s) as today_events,
                    COUNT(DISTINCT session_id) FILTER (WHERE session_id IS NOT NULL) as unique_sessions,
                    AVG((properties->>'time_on_page')::float) FILTER (WHERE event_type = 'page_exit' AND (properties->>'time_on_page') IS NOT NULL) as avg_time,
                    AVG((properties->>'load_time')::float) FILTER (WHERE event_type = 'performance') as avg_load,
                    AVG((properties->>'ttfb')::float) FILTER (WHERE event_type = 'performance') as avg_ttfb
                FROM pixel_events
                WHERE site_id = %s AND created_at >= %s
                """,
                (today, site_id, since)
            )
            res = cursor.fetchone()

            # Query 2: Bounce Rate (Aislada por costo de agregación)
            # Usamos subquery para forzar el uso del índice en session_id
            cursor.execute(
                """
                SELECT 
                    COUNT(*) as total_sessions,
                    COUNT(*) FILTER (WHERE pv_count = 1) as bounced_sessions
                FROM (
                    SELECT session_id, COUNT(*) FILTER (WHERE event_type = 'page_view') as pv_count
                    FROM pixel_events 
                    WHERE site_id = %s AND session_id IS NOT NULL AND created_at >= %s
                    GROUP BY session_id
                ) AS s
                """,
                (site_id, since)
            )
            bounce_res = cursor.fetchone()

            # Query 3: Top Pages
            cursor.execute(
                """
                SELECT url, COUNT(*) as views FROM pixel_events
                WHERE site_id = %s AND event_type = 'page_view' AND created_at >= %s
                GROUP BY url ORDER BY views DESC LIMIT 10
                """,
                (site_id, since)
            )
            top_pages = [dict(r) for r in cursor.fetchall()]

            total_sessions = bounce_res["total_sessions"] or 0
            bounced = bounce_res["bounced_sessions"] or 0
            bounce_rate = round((float(bounced) / total_sessions * 100), 1) if total_sessions > 0 else 0

            return {
                "total_events": res["total_events"] or 0,
                "today_events": res["today_events"] or 0,
                "unique_sessions": res["unique_sessions"] or 0,
                "bounce_rate": bounce_rate,
                "avg_time_on_page": round(float(res["avg_time"] or 0), 1),
                "performance": {
                    "avg_load_ms": round(float(res["avg_load"] or 0), 0),
                    "avg_ttfb_ms": round(float(res["avg_ttfb"] or 0), 0),
                },
                "top_pages": top_pages,
            }
        finally:
            release_connection(conn)

    def delete_site(self, site_id: str, user_id: int):
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM pixel_sites WHERE site_id = %s AND user_id = %s", (site_id, user_id))
            cursor.execute("DELETE FROM pixel_events WHERE site_id = %s", (site_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
