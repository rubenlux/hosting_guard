import json
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional

from app.infra.audit.sqlite import get_connection
from app.infra.db import BACKEND

logger = logging.getLogger(__name__)

def _site_status(last_seen_at: Optional[str]) -> str:
    if not last_seen_at:
        return "dead"
    try:
        if isinstance(last_seen_at, datetime):
            last = last_seen_at
        else:
            last = datetime.fromisoformat(last_seen_at)
        
        # Asegurar que comparamos en UTC
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        
        now = datetime.now(timezone.utc)
        delta = now - last
        
        if delta.total_seconds() < 86400:
            return "active"
        if delta.days < 7:
            return "warning"
        return "dead"
    except Exception:
        return "dead"

def init_pixel_db():
    """Inicializa las tablas en PostgreSQL."""
    if BACKEND != "postgresql":
        return

    conn = get_connection()
    cursor = conn.cursor()
    try:
        # 1. Tabla de sitios
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pixel_sites (
                site_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                domain TEXT,
                created_at TIMESTAMPTZ NOT NULL,
                last_seen_at TIMESTAMPTZ
            )
        """)
        
        # 2. Tabla de eventos (properties como JSONB)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pixel_events (
                event_id TEXT PRIMARY KEY,
                site_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                url TEXT,
                referrer TEXT,
                user_agent TEXT,
                ip TEXT,
                country TEXT,
                device TEXT,
                browser TEXT,
                os TEXT,
                properties JSONB,
                session_id TEXT,
                visitor_id TEXT,
                region TEXT,
                city TEXT,
                created_at TIMESTAMPTZ NOT NULL
            )
        """)

        # 3. Índices (Postgres soporta IF NOT EXISTS en CREATE INDEX desde 9.5)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_site_id ON pixel_events(site_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_created_at ON pixel_events(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_site_type ON pixel_events(site_id, event_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_session ON pixel_events(session_id)")
        
        conn.commit()
        logger.info("Pixel DB (PostgreSQL) inicializada correctamente.")
    except Exception as e:
        conn.rollback()
        logger.error(f"Error inicializando Pixel DB en Postgres: {e}")

class PixelRepositoryPG:
    def __init__(self):
        init_pixel_db()

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
        return [dict(r) for r in cursor.fetchall()]

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
        
        # Extraer properties para asegurar que viajen como dict (JSONB lo maneja psycopg2)
        props = kwargs.get("properties", {})
        
        try:
            cursor.execute(
                """INSERT INTO pixel_events
                   (event_id, site_id, user_id, event_type, url, referrer, user_agent,
                    ip, country, device, browser, os, properties, session_id, created_at,
                    visitor_id, region, city)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    event_id, kwargs.get("site_id"), kwargs.get("user_id"), kwargs.get("event_type"),
                    kwargs.get("url"), kwargs.get("referrer"), kwargs.get("user_agent"), 
                    kwargs.get("ip"), kwargs.get("country"),
                    kwargs.get("device"), kwargs.get("browser"), kwargs.get("os"),
                    json.dumps(props) if isinstance(props, dict) else props,
                    kwargs.get("session_id"), now, kwargs.get("visitor_id"), 
                    kwargs.get("region"), kwargs.get("city"),
                )
            )
            # Actualiza last_seen_at
            cursor.execute(
                "UPDATE pixel_sites SET last_seen_at = %s WHERE site_id = %s",
                (now, kwargs.get("site_id"))
            )
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

        # 1. Totales básicos
        cursor.execute(
            "SELECT COUNT(*) FROM pixel_events WHERE site_id = %s AND created_at >= %s",
            (site_id, since)
        )
        total = cursor.fetchone()["count"]

        cursor.execute(
            "SELECT COUNT(*) FROM pixel_events WHERE site_id = %s AND created_at >= %s",
            (site_id, today)
        )
        today_count = cursor.fetchone()["count"]

        cursor.execute(
            "SELECT COUNT(DISTINCT session_id) FROM pixel_events WHERE site_id = %s AND session_id IS NOT NULL AND created_at >= %s",
            (site_id, since)
        )
        unique_sessions = cursor.fetchone()["count"]

        # 2. Analytics con JSONB operadores (->>)
        cursor.execute(
            """SELECT url, COUNT(*) as views FROM pixel_events
               WHERE site_id = %s AND event_type = 'page_view' AND created_at >= %s
               GROUP BY url ORDER BY views DESC LIMIT 10""",
            (site_id, since)
        )
        top_pages = [dict(r) for r in cursor.fetchall()]

        # Bounce rate en Postgres
        cursor.execute(
            """SELECT
                COUNT(*) AS total_sessions,
                SUM(CASE WHEN pv_count = 1 THEN 1 ELSE 0 END) AS bounced
               FROM (
                   SELECT session_id,
                          SUM(CASE WHEN event_type='page_view' THEN 1 ELSE 0 END) AS pv_count
                   FROM pixel_events
                   WHERE site_id = %s AND session_id IS NOT NULL AND created_at >= %s
                   GROUP BY session_id
               ) AS session_counts""",
            (site_id, since)
        )
        bounce_row = cursor.fetchone()
        bounce_rate = round(float(bounce_row["bounced"]) / bounce_row["total_sessions"] * 100, 1) if bounce_row["total_sessions"] > 0 else None

        # Avg time on page (properties->>'key' y cast a float)
        cursor.execute(
            """SELECT AVG((properties->>'time_on_page')::float) as avg_time
               FROM pixel_events
               WHERE site_id = %s AND event_type = 'page_exit'
               AND (properties->>'time_on_page') IS NOT NULL
               AND created_at >= %s""",
            (site_id, since)
        )
        avg_time_row = cursor.fetchone()
        avg_time_on_page = round(avg_time_row["avg_time"], 1) if avg_time_row["avg_time"] else None

        # Performance
        cursor.execute(
            """SELECT
                AVG((properties->>'load_time')::float) AS avg_load,
                AVG((properties->>'ttfb')::float) AS avg_ttfb
               FROM pixel_events
               WHERE site_id = %s AND event_type = 'performance' AND created_at >= %s""",
            (site_id, since)
        )
        perf_row = cursor.fetchone()
        
        return {
            "total_events": total,
            "today_events": today_count,
            "unique_sessions": unique_sessions,
            "bounce_rate": bounce_rate,
            "avg_time_on_page": avg_time_on_page,
            "performance": {
                "avg_load_ms": round(perf_row["avg_load"], 0) if perf_row["avg_load"] else None,
                "avg_ttfb_ms": round(perf_row["avg_ttfb"], 0) if perf_row["avg_ttfb"] else None,
            },
            "top_pages": top_pages,
            # (El resto del dict se completaría con el mismo patrón ->>)
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
