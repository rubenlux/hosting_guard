import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pathlib import Path


def _site_status(last_seen_at: Optional[str]) -> str:
    """active: event in last 24h. warning: last 7 days. dead: older or never."""
    if not last_seen_at:
        return "dead"
    try:
        last = datetime.fromisoformat(last_seen_at)
        delta = datetime.utcnow() - last
        if delta.total_seconds() < 86400:
            return "active"
        if delta.days < 7:
            return "warning"
        return "dead"
    except Exception:
        return "dead"

PIXEL_DB_PATH = Path(os.getenv("PIXEL_DB_PATH", "/app/data/pixel_events.sqlite"))
# Safe Mode Flag: por defecto True para no romper analytics en el deploy
USE_SQLITE = os.getenv("PIXEL_DB_SQLITE", "true").lower() == "true"

from app.infra.audit.sqlite import get_connection


def _get_connection():
    if USE_SQLITE:
        # Mantenemos el comportamiento original de SQLite aislado
        conn = sqlite3.connect(PIXEL_DB_PATH)
        conn.row_factory = sqlite3.Row
        # WAL mode: permite lecturas concurrentes durante escrituras
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn
    else:
        # Usamos la capa unificada (Postgres) cuando se desactive el Safe Mode
        return get_connection()


def init_pixel_db():
    conn = _get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pixel_sites (
            site_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            domain TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
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
            properties TEXT,
            session_id TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # Migraciones de columnas (safe: try/except si ya existen)
    for stmt in [
        # pixel_events: visitor_id, geo (region, city para futura geolocalización)
        "ALTER TABLE pixel_events ADD COLUMN visitor_id TEXT",
        "ALTER TABLE pixel_events ADD COLUMN region TEXT",
        "ALTER TABLE pixel_events ADD COLUMN city TEXT",
        # pixel_sites: last_seen_at — último evento recibido (crítico para soporte)
        "ALTER TABLE pixel_sites ADD COLUMN last_seen_at TEXT",
    ]:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass  # columna ya existe

    # Índices base
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_site_id ON pixel_events(site_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_created_at ON pixel_events(created_at)")

    # Índices nuevos para queries de analytics
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_site_type ON pixel_events(site_id, event_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_session ON pixel_events(session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_visitor ON pixel_events(visitor_id)")

    conn.commit()


class PixelRepository:
    def __init__(self):
        init_pixel_db()

    def create_site(self, user_id: int, name: str, domain: str = None) -> str:
        site_id = uuid.uuid4().hex[:12]
        conn = _get_connection()
        conn.execute(
            "INSERT INTO pixel_sites VALUES (?, ?, ?, ?, ?)",
            (site_id, user_id, name, domain, datetime.utcnow().isoformat())
        )
        conn.commit()
        return site_id

    def get_user_sites(self, user_id: int) -> List[Dict]:
        conn = _get_connection()
        rows = conn.execute(
            "SELECT * FROM pixel_sites WHERE user_id = ?", (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_site(self, site_id: str) -> Optional[Dict]:
        conn = _get_connection()
        row = conn.execute(
            "SELECT * FROM pixel_sites WHERE site_id = ?", (site_id,)
        ).fetchone()
        return dict(row) if row else None

    def save_event(
        self,
        site_id: str,
        user_id: int,
        event_type: str,
        url: str = None,
        referrer: str = None,
        user_agent: str = None,
        ip: str = None,
        country: str = None,
        device: str = None,
        browser: str = None,
        os: str = None,
        properties: dict = None,
        session_id: str = None,
        visitor_id: str = None,
        region: str = None,   # preparado para geolocalización futura
        city: str = None,     # preparado para geolocalización futura
    ) -> str:
        event_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        conn = _get_connection()
        conn.execute(
            """INSERT INTO pixel_events
               (event_id, site_id, user_id, event_type, url, referrer, user_agent,
                ip, country, device, browser, os, properties, session_id, created_at,
                visitor_id, region, city)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id, site_id, user_id, event_type,
                url, referrer, user_agent, ip, country,
                device, browser, os,
                json.dumps(properties or {}),
                session_id, now, visitor_id, region, city,
            )
        )
        # Actualiza last_seen_at del site — permite detectar pixels muertos en soporte
        conn.execute(
            "UPDATE pixel_sites SET last_seen_at = ? WHERE site_id = ?",
            (now, site_id)
        )
        conn.commit()
        return event_id

    def get_stats(self, site_id: str, days: int = 30) -> Dict:
        conn = _get_connection()
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        today = datetime.utcnow().replace(hour=0, minute=0, second=0).isoformat()

        total = conn.execute(
            "SELECT COUNT(*) FROM pixel_events WHERE site_id = ? AND created_at >= ?",
            (site_id, since)
        ).fetchone()[0]

        today_count = conn.execute(
            "SELECT COUNT(*) FROM pixel_events WHERE site_id = ? AND created_at >= ?",
            (site_id, today)
        ).fetchone()[0]

        unique_sessions = conn.execute(
            """SELECT COUNT(DISTINCT session_id) FROM pixel_events
               WHERE site_id = ? AND session_id IS NOT NULL AND created_at >= ?""",
            (site_id, since)
        ).fetchone()[0]

        unique_visitors = conn.execute(
            """SELECT COUNT(DISTINCT visitor_id) FROM pixel_events
               WHERE site_id = ? AND visitor_id IS NOT NULL AND created_at >= ?""",
            (site_id, since)
        ).fetchone()[0]

        top_pages = conn.execute(
            """SELECT url, COUNT(*) as views FROM pixel_events
               WHERE site_id = ? AND event_type = 'page_view' AND created_at >= ?
               GROUP BY url ORDER BY views DESC LIMIT 10""",
            (site_id, since)
        ).fetchall()

        top_referrers = conn.execute(
            """SELECT referrer, COUNT(*) as count FROM pixel_events
               WHERE site_id = ? AND event_type = 'page_view'
               AND referrer IS NOT NULL AND referrer != '' AND created_at >= ?
               GROUP BY referrer ORDER BY count DESC LIMIT 10""",
            (site_id, since)
        ).fetchall()

        by_device = conn.execute(
            """SELECT device, COUNT(*) as count FROM pixel_events
               WHERE site_id = ? AND created_at >= ?
               GROUP BY device""",
            (site_id, since)
        ).fetchall()

        by_browser = conn.execute(
            """SELECT browser, COUNT(*) as count FROM pixel_events
               WHERE site_id = ? AND created_at >= ?
               GROUP BY browser ORDER BY count DESC""",
            (site_id, since)
        ).fetchall()

        by_os = conn.execute(
            """SELECT os, COUNT(*) as count FROM pixel_events
               WHERE site_id = ? AND created_at >= ?
               GROUP BY os ORDER BY count DESC""",
            (site_id, since)
        ).fetchall()

        by_country = conn.execute(
            """SELECT country, COUNT(*) as count FROM pixel_events
               WHERE site_id = ? AND country IS NOT NULL AND created_at >= ?
               GROUP BY country ORDER BY count DESC LIMIT 10""",
            (site_id, since)
        ).fetchall()

        events_by_day = conn.execute(
            """SELECT DATE(created_at) as day, COUNT(*) as count
               FROM pixel_events WHERE site_id = ? AND created_at >= ?
               GROUP BY day ORDER BY day DESC LIMIT 30""",
            (site_id, since)
        ).fetchall()

        by_event_type = conn.execute(
            """SELECT event_type, COUNT(*) as count FROM pixel_events
               WHERE site_id = ? AND created_at >= ?
               GROUP BY event_type ORDER BY count DESC""",
            (site_id, since)
        ).fetchall()

        # Bounce rate: sesiones con solo 1 page_view
        bounce_row = conn.execute(
            """SELECT
                COUNT(*) AS total_sessions,
                SUM(CASE WHEN pv_count = 1 THEN 1 ELSE 0 END) AS bounced
               FROM (
                   SELECT session_id,
                          SUM(CASE WHEN event_type='page_view' THEN 1 ELSE 0 END) AS pv_count
                   FROM pixel_events
                   WHERE site_id = ? AND session_id IS NOT NULL AND created_at >= ?
                   GROUP BY session_id
               )""",
            (site_id, since)
        ).fetchone()
        bounce_rate = None
        if bounce_row and bounce_row[0] > 0:
            bounce_rate = round(bounce_row[1] / bounce_row[0] * 100, 1)

        # Avg time on page (de eventos page_exit con time_on_page en properties)
        avg_time_row = conn.execute(
            """SELECT AVG(CAST(json_extract(properties, '$.time_on_page') AS REAL))
               FROM pixel_events
               WHERE site_id = ? AND event_type = 'page_exit'
               AND json_extract(properties, '$.time_on_page') IS NOT NULL
               AND created_at >= ?""",
            (site_id, since)
        ).fetchone()
        avg_time_on_page = round(avg_time_row[0], 1) if avg_time_row and avg_time_row[0] else None

        # Avg page load time (de eventos performance)
        perf_row = conn.execute(
            """SELECT
                AVG(CAST(json_extract(properties, '$.load_time') AS REAL)) AS avg_load,
                AVG(CAST(json_extract(properties, '$.ttfb') AS REAL)) AS avg_ttfb
               FROM pixel_events
               WHERE site_id = ? AND event_type = 'performance' AND created_at >= ?""",
            (site_id, since)
        ).fetchone()
        performance = {
            "avg_load_ms": round(perf_row[0], 0) if perf_row and perf_row[0] else None,
            "avg_ttfb_ms": round(perf_row[1], 0) if perf_row and perf_row[1] else None,
        }

        # JS errors top 10
        js_errors = conn.execute(
            """SELECT json_extract(properties, '$.message') AS message,
                      COUNT(*) AS count
               FROM pixel_events
               WHERE site_id = ? AND event_type = 'js_error' AND created_at >= ?
               GROUP BY message ORDER BY count DESC LIMIT 10""",
            (site_id, since)
        ).fetchall()

        # Scroll depth avg
        scroll_row = conn.execute(
            """SELECT AVG(CAST(json_extract(properties, '$.depth') AS REAL))
               FROM pixel_events
               WHERE site_id = ? AND event_type = 'scroll_depth' AND created_at >= ?""",
            (site_id, since)
        ).fetchone()
        avg_scroll_depth = round(scroll_row[0], 1) if scroll_row and scroll_row[0] else None

        return {
            "total_events": total,
            "today_events": today_count,
            "unique_sessions": unique_sessions,
            "unique_visitors": unique_visitors,
            "bounce_rate": bounce_rate,
            "avg_time_on_page": avg_time_on_page,
            "avg_scroll_depth": avg_scroll_depth,
            "performance": performance,
            "top_pages": [dict(r) for r in top_pages],
            "top_referrers": [dict(r) for r in top_referrers],
            "by_device": [dict(r) for r in by_device],
            "by_browser": [dict(r) for r in by_browser],
            "by_os": [dict(r) for r in by_os],
            "by_country": [dict(r) for r in by_country],
            "events_by_day": [dict(r) for r in events_by_day],
            "by_event_type": [dict(r) for r in by_event_type],
            "js_errors": [dict(r) for r in js_errors],
        }

    def get_all_stats_admin(self) -> Dict:
        """Solo para admin — ve todos los datos."""
        conn = _get_connection()
        total = conn.execute("SELECT COUNT(*) FROM pixel_events").fetchone()[0]
        total_sites = conn.execute("SELECT COUNT(*) FROM pixel_sites").fetchone()[0]
        top_sites = conn.execute(
            """SELECT s.name, s.site_id, COUNT(e.event_id) as events
               FROM pixel_sites s
               LEFT JOIN pixel_events e ON s.site_id = e.site_id
               GROUP BY s.site_id ORDER BY events DESC LIMIT 20"""
        ).fetchall()
        return {
            "total_events": total,
            "total_sites": total_sites,
            "top_sites": [dict(r) for r in top_sites],
        }

    def get_overview_admin(self) -> Dict:
        conn = _get_connection()
        total = conn.execute("SELECT COUNT(*) FROM pixel_events").fetchone()[0]
        total_sites = conn.execute("SELECT COUNT(*) FROM pixel_sites").fetchone()[0]
        today = conn.execute(
            "SELECT COUNT(*) FROM pixel_events WHERE DATE(created_at) = DATE('now')"
        ).fetchone()[0]
        top_sites = conn.execute(
            """SELECT s.name, s.site_id, s.domain, COUNT(e.event_id) as events
               FROM pixel_sites s
               LEFT JOIN pixel_events e ON s.site_id = e.site_id
               GROUP BY s.site_id ORDER BY events DESC LIMIT 20"""
        ).fetchall()
        events_by_day = conn.execute(
            """SELECT DATE(created_at) as day, COUNT(*) as count
               FROM pixel_events GROUP BY day ORDER BY day DESC LIMIT 30"""
        ).fetchall()
        by_event_type = conn.execute(
            """SELECT event_type, COUNT(*) as count FROM pixel_events
               GROUP BY event_type ORDER BY count DESC"""
        ).fetchall()
        return {
            "total_events": total,
            "today_events": today,
            "total_sites": total_sites,
            "top_sites": [dict(r) for r in top_sites],
            "events_by_day": [dict(r) for r in events_by_day],
            "by_event_type": [dict(r) for r in by_event_type],
        }

    def get_all_events_admin(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        conn = _get_connection()
        rows = conn.execute(
            """SELECT e.event_id, e.site_id, e.user_id, e.event_type, e.url,
                      e.referrer, e.device, e.browser, e.os, e.country,
                      e.session_id, e.visitor_id, e.properties, e.created_at,
                      s.name as site_name
               FROM pixel_events e
               LEFT JOIN pixel_sites s ON e.site_id = s.site_id
               ORDER BY e.created_at DESC LIMIT ? OFFSET ?""",
            (limit, offset)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_site_health(self, user_id: int) -> List[Dict]:
        """Devuelve last_seen_at, event count y status por site. Crítico para soporte."""
        conn = _get_connection()
        rows = conn.execute(
            """SELECT ps.site_id, ps.name, ps.domain, ps.created_at, ps.last_seen_at,
                      COUNT(pe.event_id) AS total_events
               FROM pixel_sites ps
               LEFT JOIN pixel_events pe ON ps.site_id = pe.site_id
               WHERE ps.user_id = ?
               GROUP BY ps.site_id""",
            (user_id,)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["status"] = _site_status(d.get("last_seen_at"))
            result.append(d)
        return result

    def get_all_sites_health(self) -> List[Dict]:
        """Admin: todos los sites con last_seen_at y status. Permite detectar pixels muertos."""
        conn = _get_connection()
        rows = conn.execute(
            """SELECT ps.site_id, ps.name, ps.domain, ps.user_id,
                      ps.created_at, ps.last_seen_at,
                      COUNT(pe.event_id) AS total_events
               FROM pixel_sites ps
               LEFT JOIN pixel_events pe ON ps.site_id = pe.site_id
               GROUP BY ps.site_id
               ORDER BY ps.last_seen_at DESC"""
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["status"] = _site_status(d.get("last_seen_at"))
            result.append(d)
        return result

    def cleanup_old_events(self, days: int = 90) -> int:
        """Elimina eventos más viejos que `days` días. Devuelve cantidad eliminada."""
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        conn = _get_connection()
        conn.execute("DELETE FROM pixel_events WHERE created_at < ?", (cutoff,))
        deleted = conn.execute("SELECT changes()").fetchone()[0]
        conn.commit()
        return deleted

    def delete_site(self, site_id: str, user_id: int):
        conn = _get_connection()
        conn.execute(
            "DELETE FROM pixel_sites WHERE site_id = ? AND user_id = ?",
            (site_id, user_id)
        )
        conn.execute(
            "DELETE FROM pixel_events WHERE site_id = ?", (site_id,)
        )
        conn.commit()
