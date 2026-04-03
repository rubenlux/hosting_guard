from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

from app.infra.audit.sqlite import get_connection, release_connection, init_db


class MetricsRepository:
    def __init__(self):
        init_db()

    def save_traffic_snapshot(
        self,
        container_name: str,
        total_requests: int,
        errors_4xx: int,
        errors_5xx: int,
    ) -> None:
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO traffic_stats (container_name, collected_at, total_requests, errors_4xx, errors_5xx) "
                "VALUES (?, ?, ?, ?, ?)",
                (container_name, datetime.now(timezone.utc).isoformat(), total_requests, errors_4xx, errors_5xx),
            )
            conn.commit()
            # Keep only last 7 days of traffic snapshots per container
            conn.execute(
                "DELETE FROM traffic_stats WHERE container_name = ? AND collected_at < ?",
                (container_name, (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()),
            )
            conn.commit()
        finally:
            release_connection()

    def get_traffic_stats(self, container_name: str, hours: int = 24) -> Dict:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT COALESCE(SUM(total_requests),0), COALESCE(SUM(errors_4xx),0), COALESCE(SUM(errors_5xx),0) "
                "FROM traffic_stats WHERE container_name = ? AND collected_at >= ?",
                (container_name, since),
            ).fetchone()
            total, e4xx, e5xx = (row[0], row[1], row[2]) if row else (0, 0, 0)
            return {"total_requests": total, "errors_4xx": e4xx, "errors_5xx": e5xx}
        finally:
            release_connection()

    def save_uptime_check(
        self,
        hosting_id: int,
        is_up: bool,
        response_ms: Optional[int] = None,
        status_code: Optional[int] = None,
    ) -> None:
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO uptime_checks (hosting_id, checked_at, is_up, response_ms, status_code) "
                "VALUES (?, ?, ?, ?, ?)",
                (hosting_id, datetime.now(timezone.utc).isoformat(), 1 if is_up else 0, response_ms, status_code),
            )
            conn.commit()
            # Keep only last 7 days of uptime checks per hosting
            conn.execute(
                "DELETE FROM uptime_checks WHERE hosting_id = ? AND checked_at < ?",
                (hosting_id, (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()),
            )
            conn.commit()
        finally:
            release_connection()

    def get_uptime_percentage(self, hosting_id: int, hours: int = 24) -> Optional[float]:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(is_up), 0) FROM uptime_checks "
                "WHERE hosting_id = ? AND checked_at >= ?",
                (hosting_id, since),
            ).fetchone()
            total, up = (row[0], row[1]) if row else (0, 0)
            if total == 0:
                return None  # no data yet
            return round((up / total) * 100, 1)
        finally:
            release_connection()

    def get_recent_uptime_checks(self, hosting_id: int, limit: int = 50) -> List[Dict]:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT checked_at, is_up, response_ms, status_code FROM uptime_checks "
                "WHERE hosting_id = ? ORDER BY checked_at DESC LIMIT ?",
                (hosting_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            release_connection()

    def get_avg_response_ms(self, hosting_id: int, hours: int = 24) -> Optional[float]:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT AVG(response_ms) FROM uptime_checks "
                "WHERE hosting_id = ? AND checked_at >= ? AND response_ms IS NOT NULL",
                (hosting_id, since),
            ).fetchone()
            val = row[0] if row else None
            return round(val, 1) if val is not None else None
        finally:
            release_connection()
