import json
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

def _site_status(last_seen_at) -> str:
    if not last_seen_at: return "dead"
    try:
        last = last_seen_at if isinstance(last_seen_at, datetime) else datetime.fromisoformat(str(last_seen_at))
        if last.tzinfo is None: last = last.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - last
        if delta.total_seconds() < 86400: return "active"
        if delta.days < 7: return "warning"
        return "dead"
    except Exception: return "dead"


class PixelRepository:
    """Implementación PostgreSQL para Analytics."""

    def create_site(self, user_id: int, name: str, domain: str = None) -> str:
        from app.infra.db import get_connection, release_connection
        site_id = uuid.uuid4().hex[:12]
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
        from app.infra.db import get_connection, release_connection
        event_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
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

            # Query 1: métricas principales
            cursor.execute(
                """
                SELECT
                    COUNT(*) AS total_events,
                    COUNT(*) FILTER (WHERE created_at >= %s) AS today_events,
                    COUNT(DISTINCT session_id) FILTER (WHERE session_id IS NOT NULL) AS unique_sessions,
                    AVG((properties->>'time_on_page')::float)
                        FILTER (WHERE event_type = 'page_exit' AND (properties->>'time_on_page') IS NOT NULL) AS avg_time,
                    AVG((properties->>'load_time')::float) FILTER (WHERE event_type = 'performance') AS avg_load,
                    AVG((properties->>'ttfb')::float)      FILTER (WHERE event_type = 'performance') AS avg_ttfb
                FROM pixel_events
                WHERE site_id = %s AND created_at >= %s
                """,
                (today, site_id, since)
            )
            res = cursor.fetchone()

            # Query 2: bounce rate
            cursor.execute(
                """
                SELECT
                    COUNT(*) AS total_sessions,
                    COUNT(*) FILTER (WHERE pv_count = 1) AS bounced_sessions
                FROM (
                    SELECT session_id, COUNT(*) FILTER (WHERE event_type = 'page_view') AS pv_count
                    FROM pixel_events
                    WHERE site_id = %s AND session_id IS NOT NULL AND created_at >= %s
                    GROUP BY session_id
                ) AS s
                """,
                (site_id, since)
            )
            bounce_res = cursor.fetchone()

            # Query 3: top pages
            cursor.execute(
                """
                SELECT url, COUNT(*) AS views FROM pixel_events
                WHERE site_id = %s AND event_type = 'page_view' AND created_at >= %s
                GROUP BY url ORDER BY views DESC LIMIT 10
                """,
                (site_id, since)
            )
            top_pages = [dict(r) for r in cursor.fetchall()]

            # Query 4: por dispositivo
            cursor.execute(
                """
                SELECT device, COUNT(*) AS count FROM pixel_events
                WHERE site_id = %s AND created_at >= %s AND device IS NOT NULL
                GROUP BY device ORDER BY count DESC
                """,
                (site_id, since)
            )
            by_device = [dict(r) for r in cursor.fetchall()]

            # Query 5: por país
            cursor.execute(
                """
                SELECT country, COUNT(*) AS count FROM pixel_events
                WHERE site_id = %s AND created_at >= %s AND country IS NOT NULL
                GROUP BY country ORDER BY count DESC LIMIT 10
                """,
                (site_id, since)
            )
            by_country = [dict(r) for r in cursor.fetchall()]

            # Query 6: serie temporal diaria (últimos `days` días)
            cursor.execute(
                """
                SELECT
                    date_trunc('day', created_at)::date AS day,
                    COUNT(*) AS events
                FROM pixel_events
                WHERE site_id = %s AND event_type = 'page_view' AND created_at >= %s
                GROUP BY day ORDER BY day
                """,
                (site_id, since)
            )
            events_by_day = [{"day": str(r["day"]), "events": r["events"]} for r in cursor.fetchall()]

            total_sessions = bounce_res["total_sessions"] or 0
            bounced = bounce_res["bounced_sessions"] or 0
            bounce_rate = round(float(bounced) / total_sessions * 100, 1) if total_sessions > 0 else 0

            return {
                "total_events":      res["total_events"] or 0,
                "today_events":      res["today_events"] or 0,
                "unique_sessions":   res["unique_sessions"] or 0,
                "bounce_rate":       bounce_rate,
                "avg_time_on_page":  round(float(res["avg_time"] or 0), 1),
                "performance": {
                    "avg_load_ms": round(float(res["avg_load"] or 0), 0),
                    "avg_ttfb_ms": round(float(res["avg_ttfb"] or 0), 0),
                },
                "top_pages":    top_pages,
                "by_device":    by_device,
                "by_country":   by_country,
                "events_by_day": events_by_day,
            }
        finally:
            release_connection(conn)

    def delete_site(self, site_id: str, user_id: int):
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM pixel_sites WHERE site_id = %s AND user_id = %s", (site_id, user_id))
            cursor.execute("DELETE FROM pixel_events WHERE site_id = %s", (site_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            release_connection(conn)

    # ── Admin / health methods ──────────────────────────────────────────────

    def get_site_health(self, user_id: int) -> List[Dict]:
        """Devuelve last_seen_at + total_events por cada sitio del usuario."""
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT ps.site_id, ps.name, ps.last_seen_at,
                       COUNT(pe.event_id) AS total_events
                FROM pixel_sites ps
                LEFT JOIN pixel_events pe ON pe.site_id = ps.site_id
                WHERE ps.user_id = %s
                GROUP BY ps.site_id, ps.name, ps.last_seen_at
                """,
                (user_id,)
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            release_connection(conn)

    def get_all_stats_admin(self) -> Dict:
        """Resumen global para el panel de administración."""
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) AS total_sites FROM pixel_sites")
            sites_row = cursor.fetchone()
            cursor.execute("SELECT COUNT(*) AS total_events FROM pixel_events")
            events_row = cursor.fetchone()
            cursor.execute(
                "SELECT COUNT(*) AS today_events FROM pixel_events WHERE created_at >= current_date"
            )
            today_row = cursor.fetchone()
            cursor.execute(
                """
                SELECT event_type, COUNT(*) AS count FROM pixel_events
                GROUP BY event_type ORDER BY count DESC LIMIT 10
                """
            )
            by_type = [dict(r) for r in cursor.fetchall()]
            return {
                "total_sites":   sites_row["total_sites"],
                "total_events":  events_row["total_events"],
                "today_events":  today_row["today_events"],
                "by_event_type": by_type,
            }
        finally:
            release_connection(conn)

    def get_all_sites_health(self) -> List[Dict]:
        """Admin: todos los sitios con last_seen_at y conteo de eventos."""
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT ps.site_id, ps.name, ps.user_id, ps.last_seen_at,
                       COUNT(pe.event_id) AS total_events
                FROM pixel_sites ps
                LEFT JOIN pixel_events pe ON pe.site_id = ps.site_id
                GROUP BY ps.site_id, ps.name, ps.user_id, ps.last_seen_at
                ORDER BY ps.last_seen_at DESC NULLS LAST
                """
            )
            rows = cursor.fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["status"] = _site_status(d.get("last_seen_at"))
                result.append(d)
            return result
        finally:
            release_connection(conn)

    def cleanup_old_events(self, days: int = 90) -> int:
        """Elimina eventos más viejos que `days` días. Devuelve el número eliminado."""
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            cursor.execute(
                "DELETE FROM pixel_events WHERE created_at < %s",
                (cutoff,)
            )
            deleted = cursor.rowcount
            conn.commit()
            return deleted
        except Exception:
            conn.rollback()
            raise
        finally:
            release_connection(conn)
