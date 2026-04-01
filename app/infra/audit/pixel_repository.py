import json
import sqlite3
import uuid
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

PIXEL_DB_PATH = Path("/app/data/pixel_events.sqlite")


def _get_connection():
    conn = sqlite3.connect(PIXEL_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_events_site_id ON pixel_events(site_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_events_created_at ON pixel_events(created_at)
    """)
    conn.commit()
    conn.close()


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
        conn.close()
        return site_id

    def get_user_sites(self, user_id: int) -> List[Dict]:
        conn = _get_connection()
        rows = conn.execute(
            "SELECT * FROM pixel_sites WHERE user_id = ?", (user_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_site(self, site_id: str) -> Optional[Dict]:
        conn = _get_connection()
        row = conn.execute(
            "SELECT * FROM pixel_sites WHERE site_id = ?", (site_id,)
        ).fetchone()
        conn.close()
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
    ) -> str:
        event_id = str(uuid.uuid4())
        conn = _get_connection()
        conn.execute(
            """INSERT INTO pixel_events VALUES
               (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id, site_id, user_id, event_type,
                url, referrer, user_agent, ip, country,
                device, browser, os,
                json.dumps(properties or {}),
                session_id,
                datetime.utcnow().isoformat()
            )
        )
        conn.commit()
        conn.close()
        return event_id

    def get_stats(self, site_id: str, days: int = 30) -> Dict:
        conn = _get_connection()
        from_date = datetime.utcnow().replace(
            hour=0, minute=0, second=0
        ).isoformat()

        total = conn.execute(
            "SELECT COUNT(*) FROM pixel_events WHERE site_id = ?",
            (site_id,)
        ).fetchone()[0]

        today = conn.execute(
            "SELECT COUNT(*) FROM pixel_events WHERE site_id = ? AND created_at >= ?",
            (site_id, from_date)
        ).fetchone()[0]

        top_pages = conn.execute(
            """SELECT url, COUNT(*) as views FROM pixel_events
               WHERE site_id = ? AND event_type = 'page_view'
               GROUP BY url ORDER BY views DESC LIMIT 10""",
            (site_id,)
        ).fetchall()

        by_device = conn.execute(
            """SELECT device, COUNT(*) as count FROM pixel_events
               WHERE site_id = ?
               GROUP BY device""",
            (site_id,)
        ).fetchall()

        by_country = conn.execute(
            """SELECT country, COUNT(*) as count FROM pixel_events
               WHERE site_id = ? AND country IS NOT NULL
               GROUP BY country ORDER BY count DESC LIMIT 10""",
            (site_id,)
        ).fetchall()

        events_by_day = conn.execute(
            """SELECT DATE(created_at) as day, COUNT(*) as count
               FROM pixel_events WHERE site_id = ?
               GROUP BY day ORDER BY day DESC LIMIT 30""",
            (site_id,)
        ).fetchall()

        unique_sessions = conn.execute(
            """SELECT COUNT(DISTINCT session_id) FROM pixel_events
               WHERE site_id = ? AND session_id IS NOT NULL""",
            (site_id,)
        ).fetchone()[0]

        conn.close()
        return {
            "total_events": total,
            "today_events": today,
            "unique_sessions": unique_sessions,
            "top_pages": [dict(r) for r in top_pages],
            "by_device": [dict(r) for r in by_device],
            "by_country": [dict(r) for r in by_country],
            "events_by_day": [dict(r) for r in events_by_day],
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
        conn.close()
        return {
            "total_events": total,
            "total_sites": total_sites,
            "top_sites": [dict(r) for r in top_sites],
        }

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
        conn.close()
