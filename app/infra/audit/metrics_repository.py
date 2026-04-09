from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from app.infra.db import get_connection, reset_pg_connection
from app.infra.migrations import init_db

class MetricsRepository:
    """Implementación PostgreSQL limpia para Métricas y Uptime."""
    def __init__(self):
        init_db()

    def save_traffic_snapshot(self, container_name: str, total_requests: int, errors_4xx: int, errors_5xx: int) -> None:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO traffic_stats (container_name, collected_at, total_requests, errors_4xx, errors_5xx) "
                "VALUES (%s, %s, %s, %s, %s)",
                (container_name, datetime.now(timezone.utc).isoformat(), total_requests, errors_4xx, errors_5xx),
            )
            # Limpiar snapshots de más de 7 días
            cursor.execute(
                "DELETE FROM traffic_stats WHERE container_name = %s AND collected_at < %s",
                (container_name, (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()),
            )
            conn.commit()
        finally:
            reset_pg_connection()

    def get_traffic_stats(self, container_name: str, hours: int = 24) -> Dict:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COALESCE(SUM(total_requests),0) AS total, "
                "COALESCE(SUM(errors_4xx),0) AS e4xx, "
                "COALESCE(SUM(errors_5xx),0) AS e5xx "
                "FROM traffic_stats WHERE container_name = %s AND collected_at >= %s",
                (container_name, since),
            )
            row = cursor.fetchone()
            if row:
                return {"total_requests": row["total"], "errors_4xx": row["e4xx"], "errors_5xx": row["e5xx"]}
            return {"total_requests": 0, "errors_4xx": 0, "errors_5xx": 0}
        finally:
            reset_pg_connection()

    def save_uptime_check(self, hosting_id: int, is_up: bool, response_ms: Optional[int] = None, status_code: Optional[int] = None) -> None:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO uptime_checks (hosting_id, checked_at, is_up, response_ms, status_code) "
                "VALUES (%s, %s, %s, %s, %s)",
                (hosting_id, datetime.now(timezone.utc).isoformat(), 1 if is_up else 0, response_ms, status_code),
            )
            cursor.execute(
                "DELETE FROM uptime_checks WHERE hosting_id = %s AND checked_at < %s",
                (hosting_id, (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()),
            )
            conn.commit()
        finally:
            reset_pg_connection()

    def get_uptime_percentage(self, hosting_id: int, hours: int = 24) -> Optional[float]:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) AS total, COALESCE(SUM(is_up), 0) AS up_count "
                "FROM uptime_checks WHERE hosting_id = %s AND checked_at >= %s",
                (hosting_id, since),
            )
            row = cursor.fetchone()
            total = row["total"] if row else 0
            up = row["up_count"] if row else 0
            return round((up / total) * 100, 1) if total > 0 else None
        finally:
            reset_pg_connection()

    def get_recent_uptime_checks(self, hosting_id: int, limit: int = 50) -> List[Dict]:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT checked_at, is_up, response_ms, status_code FROM uptime_checks "
                "WHERE hosting_id = %s ORDER BY checked_at DESC LIMIT %s",
                (hosting_id, limit),
            )
            return [dict(r) for r in cursor.fetchall()]
        finally:
            reset_pg_connection()

    def get_avg_response_ms(self, hosting_id: int, hours: int = 24) -> Optional[float]:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT AVG(response_ms) AS avg_ms FROM uptime_checks "
                "WHERE hosting_id = %s AND checked_at >= %s AND response_ms IS NOT NULL",
                (hosting_id, since),
            )
            row = cursor.fetchone()
            val = row["avg_ms"] if row else None
            return round(float(val), 1) if val is not None else None
        finally:
            reset_pg_connection()
