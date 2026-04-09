import json
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from app.infra.db import get_connection
from app.infra.migrations import init_db

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
    def __init__(self):
        init_db()

    def create_site(self, user_id: int, name: str, domain: str = None) -> str:
        site_id = uuid.uuid4().hex[:12]
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO pixel_sites (site_id, user_id, name, domain, created_at) VALUES (%s, %s, %s, %s, %s)",
                (site_id, user_id, name, domain, datetime.now(timezone.utc))
            )
            conn.commit()
            return site_id
        except Exception:
            conn.rollback()
            raise

    def get_user_sites(self, user_id: int) -> List[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pixel_sites WHERE user_id = %s", (user_id,))
        rows = cursor.fetchall()
        sites = []
        for r in rows:
            d = dict(r)
            d["status"] = _site_status(d.get("last_seen_at"))
            sites.append(d)
        return sites

    def get_site(self, site_id: str) -> Optional[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pixel_sites WHERE site_id = %s", (site_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def save_event(self, **kwargs) -> str:
        event_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        conn = get_connection()
        cursor = conn.cursor()
        props = kwargs.get("properties", {})
        try:
            cursor.execute(
                """INSERT INTO pixel_events
                   (event_id, site_id, user_id, event_type, url, referrer, user_agent,
                    ip, country, device, browser, os, properties, session_id, created_at,
                    visitor_id, region, city)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (event_id, kwargs.get("site_id"), kwargs.get("user_id"), kwargs.get("event_type"),
                 kwargs.get("url"), kwargs.get("referrer"), kwargs.get("user_agent"), 
                 kwargs.get("ip"), kwargs.get("country"), kwargs.get("device"), kwargs.get("browser"), 
                 kwargs.get("os"), json.dumps(props) if isinstance(props, dict) else props,
                 kwargs.get("session_id"), now, kwargs.get("visitor_id"), kwargs.get("region"), kwargs.get("city"))
            )
            cursor.execute("UPDATE pixel_sites SET last_seen_at = %s WHERE site_id = %s", (now, kwargs.get("site_id")))
            conn.commit()
            return event_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Error saving pixel event: {e}")
            raise

    def get_stats(self, site_id: str, days: int = 30) -> Dict:
        conn = get_connection()
        cursor = conn.cursor()
        since = datetime.now(timezone.utc) - timedelta(days=days)
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        cursor.execute("SELECT COUNT(*) FROM pixel_events WHERE site_id = %s AND created_at >= %s", (site_id, since))
        total = cursor.fetchone()["count"]

        cursor.execute("SELECT COUNT(*) FROM pixel_events WHERE site_id = %s AND created_at >= %s", (site_id, today))
        today_count = cursor.fetchone()["count"]

        cursor.execute("SELECT COUNT(DISTINCT session_id) FROM pixel_events WHERE site_id = %s AND session_id IS NOT NULL AND created_at >= %s", (site_id, since))
        unique_sessions = cursor.fetchone()["count"]

        cursor.execute(
            """SELECT url, COUNT(*) as views FROM pixel_events
               WHERE site_id = %s AND event_type = 'page_view' AND created_at >= %s
               GROUP BY url ORDER BY views DESC LIMIT 10""",
            (site_id, since)
        )
        top_pages = [dict(r) for r in cursor.fetchall()]

        cursor.execute(
            """SELECT COUNT(*) AS total_sessions, SUM(CASE WHEN pv_count = 1 THEN 1 ELSE 0 END) AS bounced
               FROM (SELECT session_id, SUM(CASE WHEN event_type='page_view' THEN 1 ELSE 0 END) AS pv_count
                     FROM pixel_events WHERE site_id = %s AND session_id IS NOT NULL AND created_at >= %s
                     GROUP BY session_id) AS s""", (site_id, since)
        )
        b = cursor.fetchone()
        bounce_rate = round(float(b["bounced"]) / b["total_sessions"] * 100, 1) if b and b["total_sessions"] > 0 else 0

        cursor.execute(
            """SELECT AVG((properties->>'time_on_page')::float) as avg_time FROM pixel_events
               WHERE site_id = %s AND event_type = 'page_exit' AND (properties->>'time_on_page') IS NOT NULL AND created_at >= %s""",
            (site_id, since)
        )
        a = cursor.fetchone()
        avg_time = round(float(a["avg_time"]), 1) if a and a["avg_time"] else 0

        cursor.execute(
            """SELECT AVG((properties->>'load_time')::float) AS avg_load, AVG((properties->>'ttfb')::float) AS avg_ttfb
               FROM pixel_events WHERE site_id = %s AND event_type = 'performance' AND created_at >= %s""",
            (site_id, since)
        )
        p = cursor.fetchone()
        
        return {
            "total_events": total, "today_events": today_count, "unique_sessions": unique_sessions,
            "bounce_rate": bounce_rate, "avg_time_on_page": avg_time,
            "performance": {
                "avg_load_ms": round(float(p["avg_load"]), 0) if p and p["avg_load"] else 0,
                "avg_ttfb_ms": round(float(p["avg_ttfb"]), 0) if p and p["avg_ttfb"] else 0,
            },
            "top_pages": top_pages,
        }

    def delete_site(self, site_id: str, user_id: int):
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM pixel_sites WHERE site_id = %s AND user_id = %s", (site_id, user_id))
            cursor.execute("DELETE FROM pixel_events WHERE site_id = %s", (site_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
