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

            # Query 1: métricas principales + métricas de engagement
            cursor.execute(
                """
                SELECT
                    COUNT(*) AS total_events,
                    COUNT(*) FILTER (WHERE created_at >= %s) AS today_events,
                    COUNT(DISTINCT session_id) FILTER (WHERE session_id IS NOT NULL) AS unique_sessions,
                    AVG((properties->>'time_on_page')::float)
                        FILTER (WHERE event_type = 'page_exit' AND (properties->>'time_on_page') IS NOT NULL) AS avg_time,
                    AVG((properties->>'load_time')::float) FILTER (WHERE event_type = 'performance') AS avg_load,
                    AVG((properties->>'ttfb')::float)      FILTER (WHERE event_type = 'performance') AS avg_ttfb,
                    COUNT(*) FILTER (WHERE event_type = 'page_view') AS total_page_views,
                    ROUND(
                        COUNT(*) FILTER (WHERE event_type = 'page_view')::numeric
                        / NULLIF(COUNT(DISTINCT session_id) FILTER (WHERE session_id IS NOT NULL), 0),
                    2) AS avg_pages_per_session,
                    ROUND(
                        COUNT(*)::numeric
                        / NULLIF(COUNT(DISTINCT session_id) FILTER (WHERE session_id IS NOT NULL), 0),
                    2) AS avg_events_per_session
                FROM pixel_events
                WHERE site_id = %s AND created_at >= %s
                """,
                (today, site_id, since)
            )
            res = cursor.fetchone()

            # Query 1b: usuarios activos últimos 5 min
            cursor.execute(
                """SELECT COUNT(DISTINCT COALESCE(visitor_id, session_id)) AS active_5min
                   FROM pixel_events WHERE site_id = %s
                   AND created_at >= NOW() - INTERVAL '5 minutes'""",
                (site_id,)
            )
            active_row = cursor.fetchone()

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
                "total_events":           res["total_events"] or 0,
                "today_events":           res["today_events"] or 0,
                "unique_sessions":        res["unique_sessions"] or 0,
                "bounce_rate":            bounce_rate,
                "avg_time_on_page":       round(float(res["avg_time"] or 0), 1),
                "avg_pages_per_session":  round(float(res["avg_pages_per_session"] or 0), 1),
                "avg_events_per_session": round(float(res["avg_events_per_session"] or 0), 1),
                "active_users_5min":      int(active_row["active_5min"] or 0),
                "performance": {
                    "avg_load_ms": round(float(res["avg_load"] or 0), 0),
                    "avg_ttfb_ms": round(float(res["avg_ttfb"] or 0), 0),
                },
                "top_pages":     top_pages,
                "by_device":     by_device,
                "by_country":    by_country,
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

    def get_overview_admin(self) -> Dict:
        """Admin overview — alias of get_all_stats_admin for the /admin/pixel/overview route."""
        return self.get_all_stats_admin()

    def get_all_events_admin(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        """Admin: all events across all users/sites, paginated. Powers /admin/pixel/events."""
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT pe.event_id, pe.site_id, pe.user_id, pe.event_type,
                       pe.url, pe.referrer, pe.user_agent, pe.ip,
                       pe.country, pe.device, pe.browser, pe.os,
                       pe.session_id, pe.visitor_id,
                       pe.properties, pe.created_at,
                       ps.name AS site_name
                FROM pixel_events pe
                LEFT JOIN pixel_sites ps ON ps.site_id = pe.site_id
                ORDER BY pe.created_at DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
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

    def update_event_geo(self, event_id: str, country: str,
                         region: Optional[str] = None, city: Optional[str] = None) -> None:
        """Update country/region/city on an event record after async GeoIP resolution."""
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE pixel_events SET country = %s, region = %s, city = %s WHERE event_id = %s",
                (country, region, city, event_id)
            )
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            release_connection(conn)

    def get_timeseries(self, site_id: str, days: int = 30) -> List[Dict]:
        """
        Gap-filled timeseries.
        - days <= 1  → hourly buckets for the last 24 h
        - days >  1  → daily  buckets with zeros for days with no events
        """
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc)

            if days <= 1:
                since = now - timedelta(hours=24)
                start = since.replace(minute=0, second=0, microsecond=0)
                end   = now.replace(minute=0, second=0, microsecond=0)
                cursor.execute(
                    """
                    WITH calendar AS (
                        SELECT generate_series(%s::timestamptz, %s::timestamptz, '1 hour') AS bucket
                    ),
                    data AS (
                        SELECT
                            date_trunc('hour', created_at) AS bucket,
                            COUNT(*) FILTER (WHERE event_type = 'page_view') AS page_views,
                            COUNT(DISTINCT session_id) FILTER (WHERE session_id IS NOT NULL) AS sessions
                        FROM pixel_events
                        WHERE site_id = %s AND created_at >= %s
                        GROUP BY 1
                    )
                    SELECT
                        to_char(c.bucket AT TIME ZONE 'UTC', 'HH24:MI') AS label,
                        COALESCE(d.page_views, 0) AS page_views,
                        COALESCE(d.sessions,   0) AS sessions
                    FROM calendar c LEFT JOIN data d ON c.bucket = d.bucket
                    ORDER BY c.bucket
                    """,
                    (start, end, site_id, since)
                )
                return [
                    {"day": r["label"], "label": r["label"],
                     "page_views": int(r["page_views"]), "sessions": int(r["sessions"])}
                    for r in cursor.fetchall()
                ]
            else:
                since = now - timedelta(days=days)
                cursor.execute(
                    """
                    WITH calendar AS (
                        SELECT generate_series(%s::date, %s::date, '1 day'::interval)::date AS day
                    ),
                    data AS (
                        SELECT
                            date_trunc('day', created_at)::date AS day,
                            COUNT(*) FILTER (WHERE event_type = 'page_view') AS page_views,
                            COUNT(DISTINCT session_id) FILTER (WHERE session_id IS NOT NULL) AS sessions
                        FROM pixel_events
                        WHERE site_id = %s AND created_at >= %s
                        GROUP BY 1
                    )
                    SELECT
                        c.day::text AS day,
                        COALESCE(d.page_views, 0) AS page_views,
                        COALESCE(d.sessions,   0) AS sessions
                    FROM calendar c LEFT JOIN data d ON c.day = d.day
                    ORDER BY c.day
                    """,
                    (since.date(), now.date(), site_id, since)
                )
                return [
                    {"day": r["day"], "label": r["day"][5:],   # "MM-DD"
                     "page_views": int(r["page_views"]), "sessions": int(r["sessions"])}
                    for r in cursor.fetchall()
                ]
        finally:
            release_connection(conn)

    def get_realtime(self, site_id: str) -> Dict:
        """Active users (5 min), events last 60 s, recent page views."""
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc)

            # Avoid COALESCE which prevents index use on visitor_id.
            # Sum two index-friendly counts: identified visitors + anonymous sessions.
            cursor.execute(
                """SELECT
                       COUNT(DISTINCT visitor_id)
                           FILTER (WHERE visitor_id IS NOT NULL) AS active_visitors,
                       COUNT(DISTINCT session_id)
                           FILTER (WHERE session_id IS NOT NULL AND visitor_id IS NULL) AS active_anon
                   FROM pixel_events
                   WHERE site_id = %s AND created_at >= %s""",
                (site_id, now - timedelta(minutes=5))
            )
            active_row = cursor.fetchone()

            cursor.execute(
                """SELECT COUNT(*) AS cnt FROM pixel_events
                   WHERE site_id = %s AND created_at >= %s""",
                (site_id, now - timedelta(seconds=60))
            )
            ev60_row = cursor.fetchone()

            cursor.execute(
                """SELECT url, created_at, device, country FROM pixel_events
                   WHERE site_id = %s AND event_type = 'page_view'
                   ORDER BY created_at DESC LIMIT 10""",
                (site_id,)
            )
            pages = []
            for r in cursor.fetchall():
                d = dict(r)
                d["created_at"] = d["created_at"].isoformat() if d.get("created_at") else None
                pages.append(d)

            active = int(active_row["active_visitors"] or 0) + int(active_row["active_anon"] or 0)
            return {
                "active_users": active,
                "events_60s":   int(ev60_row["cnt"] or 0),
                "recent_pages": pages,
            }
        finally:
            release_connection(conn)

    def get_funnel(self, site_id: str, days: int = 30) -> Dict:
        """Entry pages, exit pages, drop-off rate."""
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()
            since = datetime.now(timezone.utc) - timedelta(days=days)

            cursor.execute(
                """SELECT url, COUNT(*) AS entries FROM (
                       SELECT DISTINCT ON (session_id) session_id, url
                       FROM pixel_events
                       WHERE site_id = %s AND event_type = 'page_view'
                         AND session_id IS NOT NULL AND created_at >= %s
                       ORDER BY session_id, created_at ASC
                   ) first GROUP BY url ORDER BY entries DESC LIMIT 5""",
                (site_id, since)
            )
            entry_pages = [dict(r) for r in cursor.fetchall()]

            cursor.execute(
                """SELECT url, COUNT(*) AS exits FROM (
                       SELECT DISTINCT ON (session_id) session_id, url
                       FROM pixel_events
                       WHERE site_id = %s AND event_type = 'page_view'
                         AND session_id IS NOT NULL AND created_at >= %s
                       ORDER BY session_id, created_at DESC
                   ) last GROUP BY url ORDER BY exits DESC LIMIT 5""",
                (site_id, since)
            )
            exit_pages = [dict(r) for r in cursor.fetchall()]

            cursor.execute(
                """SELECT
                       COUNT(DISTINCT session_id) AS total,
                       COUNT(DISTINCT session_id) FILTER (WHERE pv_count = 1) AS single_page
                   FROM (
                       SELECT session_id,
                              COUNT(*) FILTER (WHERE event_type = 'page_view') AS pv_count
                       FROM pixel_events
                       WHERE site_id = %s AND session_id IS NOT NULL AND created_at >= %s
                       GROUP BY session_id
                   ) s""",
                (site_id, since)
            )
            dr = cursor.fetchone()
            total  = int(dr["total"]       or 0)
            single = int(dr["single_page"] or 0)
            dropoff = round(single / total * 100, 1) if total > 0 else 0

            return {
                "entry_pages":    entry_pages,
                "exit_pages":     exit_pages,
                "dropoff_rate":   dropoff,
                "total_sessions": total,
            }
        finally:
            release_connection(conn)

    def get_devices(self, site_id: str, days: int = 30) -> List[Dict]:
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()
            since = datetime.now(timezone.utc) - timedelta(days=days)
            cursor.execute(
                """
                SELECT device, COUNT(*) AS count FROM pixel_events
                WHERE site_id = %s AND created_at >= %s AND device IS NOT NULL
                GROUP BY device ORDER BY count DESC
                """,
                (site_id, since)
            )
            return [dict(r) for r in cursor.fetchall()]
        finally:
            release_connection(conn)

    def get_countries(self, site_id: str, days: int = 30) -> List[Dict]:
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()
            since = datetime.now(timezone.utc) - timedelta(days=days)
            cursor.execute(
                """
                SELECT country, COUNT(*) AS count FROM pixel_events
                WHERE site_id = %s AND created_at >= %s AND country IS NOT NULL
                GROUP BY country ORDER BY count DESC LIMIT 10
                """,
                (site_id, since)
            )
            return [dict(r) for r in cursor.fetchall()]
        finally:
            release_connection(conn)

    def get_pages(self, site_id: str, days: int = 30) -> List[Dict]:
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()
            since = datetime.now(timezone.utc) - timedelta(days=days)
            cursor.execute(
                """
                SELECT url, COUNT(*) AS views FROM pixel_events
                WHERE site_id = %s AND event_type = 'page_view' AND created_at >= %s
                GROUP BY url ORDER BY views DESC LIMIT 10
                """,
                (site_id, since)
            )
            return [dict(r) for r in cursor.fetchall()]
        finally:
            release_connection(conn)

    def get_dashboard_summary_data(self, site_id: str, days: int = 7) -> Dict:
        """
        Single-connection aggregation for the dashboard-summary endpoint.
        4 queries on one connection (down from 7):

          Query A — stats + active_5min     (1 scan, was 2 separate queries)
          Query B — bounce rate             (1 subquery scan)
          Query C — sparkline               (CTE + gap-fill)
          Query D — pages + devices + countries  (1 CTE scan, was 3 separate queries)
        """
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()
            now   = datetime.now(timezone.utc)
            since = now - timedelta(days=days)
            today = now.replace(hour=0, minute=0, second=0, microsecond=0)

            # ── Query A: stats + active_5min in one scan ───────────────────────
            # active_5min uses FILTER with the 5-minute window; the outer WHERE
            # already covers the last `days` days which includes the 5-min window.
            cursor.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE created_at >= %s)                       AS today_events,
                    COUNT(DISTINCT session_id)
                        FILTER (WHERE session_id IS NOT NULL)                      AS unique_sessions,
                    COUNT(DISTINCT visitor_id)
                        FILTER (WHERE created_at >= NOW() - INTERVAL '5 minutes'
                                AND visitor_id IS NOT NULL)                        AS active_visitors,
                    COUNT(DISTINCT session_id)
                        FILTER (WHERE created_at >= NOW() - INTERVAL '5 minutes'
                                AND session_id IS NOT NULL
                                AND visitor_id IS NULL)                            AS active_sessions_fallback
                FROM pixel_events
                WHERE site_id = %s AND created_at >= %s
                """,
                (today, site_id, since)
            )
            stats_row = cursor.fetchone()

            # ── Query B: bounce rate ───────────────────────────────────────────
            cursor.execute(
                """
                SELECT
                    COUNT(*) AS total_sessions,
                    COUNT(*) FILTER (WHERE pv_count = 1) AS bounced
                FROM (
                    SELECT session_id,
                           COUNT(*) FILTER (WHERE event_type = 'page_view') AS pv_count
                    FROM pixel_events
                    WHERE site_id = %s AND session_id IS NOT NULL AND created_at >= %s
                    GROUP BY session_id
                ) s
                """,
                (site_id, since)
            )
            bounce_row = cursor.fetchone()

            # ── Query C: sparkline — gap-filled daily timeseries ───────────────
            cursor.execute(
                """
                WITH calendar AS (
                    SELECT generate_series(%s::date, %s::date, '1 day'::interval)::date AS day
                ),
                data AS (
                    SELECT date_trunc('day', created_at)::date AS day,
                           COUNT(*) FILTER (WHERE event_type = 'page_view') AS page_views
                    FROM pixel_events
                    WHERE site_id = %s AND created_at >= %s
                    GROUP BY 1
                )
                SELECT COALESCE(d.page_views, 0) AS page_views
                FROM calendar c LEFT JOIN data d ON c.day = d.day
                ORDER BY c.day
                """,
                (since.date(), now.date(), site_id, since)
            )
            sparkline = [int(r["page_views"]) for r in cursor.fetchall()]

            # ── Query D: pages + devices + countries — single CTE scan ─────────
            # MATERIALIZED forces Postgres to execute the base scan exactly once
            # and store the result set, preventing the planner from re-scanning
            # pixel_events three times if it chooses to inline the CTE.
            # The predicates (site_id, created_at) are already pushed into `base`,
            # so the partition pruning happens before materialization.
            #
            # Tradeoff: the materialized result set is held in work_mem (default 4MB).
            # At ~200 bytes/row this handles ~20k rows comfortably before spilling to
            # disk. For a 7-day dashboard window that covers tens of thousands of
            # events this is fine. If days grows large (>90) and volume is high,
            # switch to NOT MATERIALIZED and let the planner inline it instead.
            cursor.execute(
                """
                WITH base AS MATERIALIZED (
                    SELECT event_type, url, device, country
                    FROM pixel_events
                    WHERE site_id = %s AND created_at >= %s
                )
                SELECT
                    (
                        SELECT COALESCE(json_agg(r), '[]'::json) FROM (
                            SELECT url, COUNT(*) AS views
                            FROM base WHERE event_type = 'page_view'
                            GROUP BY url ORDER BY views DESC LIMIT 3
                        ) r
                    ) AS pages,
                    (
                        SELECT COALESCE(json_agg(r), '[]'::json) FROM (
                            SELECT device, COUNT(*) AS count
                            FROM base WHERE device IS NOT NULL
                            GROUP BY device ORDER BY count DESC
                        ) r
                    ) AS devices,
                    (
                        SELECT COALESCE(json_agg(r), '[]'::json) FROM (
                            SELECT country, COUNT(*) AS count
                            FROM base WHERE country IS NOT NULL
                            GROUP BY country ORDER BY count DESC LIMIT 3
                        ) r
                    ) AS countries
                """,
                (site_id, since)
            )
            agg_row = cursor.fetchone()

            def _parse_json_col(col):
                """psycopg2 returns JSONB as dict/list already; handle both."""
                v = agg_row[col]
                if v is None:
                    return []
                if isinstance(v, list):
                    return [dict(item) for item in v]
                import json
                return json.loads(v)

            pages_raw    = _parse_json_col("pages")
            devices_raw  = _parse_json_col("devices")
            countries_raw = _parse_json_col("countries")

            # ── Assemble ───────────────────────────────────────────────────────
            total_s = int(bounce_row["total_sessions"] or 0)
            bounced = int(bounce_row["bounced"] or 0)
            bounce_rate = round(bounced / total_s * 100, 1) if total_s > 0 else 0

            # Combine visitor + session fallback to approximate active unique users
            active_5min = int(stats_row["active_visitors"] or 0) + int(stats_row["active_sessions_fallback"] or 0)

            stats = {
                "today_events":      int(stats_row["today_events"]    or 0),
                "unique_sessions":   int(stats_row["unique_sessions"]  or 0),
                "bounce_rate":       bounce_rate,
                "active_users_5min": active_5min,
            }

            return {
                "stats":         stats,
                "sparkline":     sparkline,
                "pages_raw":     pages_raw,
                "devices_raw":   devices_raw,
                "countries_raw": countries_raw,
            }
        finally:
            release_connection(conn)

    def cleanup_old_events(self, days: int = 90) -> int:
        """
        Elimina eventos más viejos que `days` días.

        Para tablas particionadas por RANGE(created_at), DROP TABLE sobre la
        partición es O(1) — instantáneo. DELETE es O(n) — escanea y marca cada
        fila como muerta, genera WAL, requiere VACUUM posterior.

        Estrategia:
          1. Detectar particiones mensuales cuyo rango completo queda antes del cutoff.
          2. DROP TABLE de cada una (instantáneo, sin WAL de rows).
          3. Si no hay particiones elegibles (tabla sin particionar o cutoff dentro
             del mes actual), caer back a DELETE para compatibilidad.

        Devuelve el número de particiones eliminadas (o -1 si se usó DELETE fallback).
        """
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

            # Find monthly partitions whose entire range is older than cutoff
            cursor.execute(
                """
                SELECT c.relname AS partition_name,
                       pg_get_expr(c.relpartbound, c.oid) AS bound
                FROM pg_class p
                JOIN pg_inherits i ON i.inhparent = p.oid
                JOIN pg_class c    ON c.oid = i.inhrelid
                WHERE p.relname = 'pixel_events'
                  AND c.relkind = 'r'
                  AND c.relname != 'pixel_events_default'
                ORDER BY c.relname
                """
            )
            partitions = cursor.fetchall()

            dropped = 0
            for row in partitions:
                name  = row["partition_name"]
                bound = row["bound"] or ""
                # Partition name format: pixel_events_YYYY_MM
                # Safe to drop only if the upper bound of the partition is <= cutoff
                # Parse the TO date from the bound expression: "FOR VALUES FROM (...) TO ('2025-02-01 ...')"
                import re
                to_match = re.search(r"TO \('([^']+)'", bound)
                if not to_match:
                    continue
                try:
                    raw = to_match.group(1).strip()
                    # Normalize PG formats to ISO 8601 so fromisoformat handles them:
                    #   "2025-02-01 00:00:00+00"    → "2025-02-01T00:00:00+00:00"
                    #   "2025-02-01 00:00:00+00:00" → "2025-02-01T00:00:00+00:00"
                    raw = raw.replace(" ", "T", 1)          # space → T separator
                    if raw.endswith("+00"):                  # +00 → +00:00
                        raw = raw[:-3] + "+00:00"
                    upper = datetime.fromisoformat(raw)
                    if upper.tzinfo is None:
                        upper = upper.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue

                if upper <= cutoff:
                    cursor.execute(f'DROP TABLE IF EXISTS "{name}"')
                    dropped += 1

            if dropped > 0:
                conn.commit()
                return dropped

            # Fallback: table is not partitioned or all data is within retention window
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
