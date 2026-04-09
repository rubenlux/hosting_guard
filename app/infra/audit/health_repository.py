import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from app.infra.db import get_connection

logger = logging.getLogger(__name__)

class HealthRepository:
    """Implementación PostgreSQL limpia para Historial de Salud Alertas."""
    def save_health_entry(self, user_id: int, site_id: int, score: int, status: str, cpu: float, ram: float,
                          error_count: int = 0, warning_count: int = 0,
                          alert_type: Optional[str] = None, alert_message: Optional[str] = None) -> bool:
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        try:
            cursor.execute(
                """INSERT INTO site_health_history 
                   (user_id, site_id, score, status, cpu, ram, 
                    error_count, warning_count, alert_type, alert_message, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (user_id, site_id, score, status, cpu, ram, 
                 error_count, warning_count, alert_type, alert_message, now)
            )
            conn.commit()
            return True
        except Exception:
            logger.exception("Failed to save health history for site_id=%s", site_id)
            conn.rollback()
            return False

    def get_latest_health(self, site_id: int) -> Optional[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM site_health_history WHERE site_id = %s ORDER BY created_at DESC LIMIT 1", (site_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_last_alert(self, site_id: int) -> Optional[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT * FROM site_health_history 
                WHERE site_id = %s AND alert_type IS NOT NULL 
                ORDER BY created_at DESC LIMIT 1""",
            (site_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_health_history(self, site_id: int, limit: int = 24) -> List[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM site_health_history WHERE site_id = %s ORDER BY created_at DESC LIMIT %s", (site_id, limit))
        rows = cursor.fetchall()
        return [dict(r) for r in reversed(rows)]

    def create_alert(self, user_id: int, site_id: int, level: str, message: str) -> bool:
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        try:
            cursor.execute(
                "INSERT INTO site_alerts (user_id, site_id, level, message, created_at) VALUES (%s, %s, %s, %s, %s)",
                (user_id, site_id, level, message, now)
            )
            conn.commit()
            return True
        except Exception:
            logger.exception("Failed to create alert for site_id=%s", site_id)
            conn.rollback()
            return False

    def get_user_alerts(self, user_id: int, limit: int = 20) -> List[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM site_alerts WHERE user_id = %s ORDER BY created_at DESC LIMIT %s", (user_id, limit))
        return [dict(r) for r in cursor.fetchall()]

    def resolve_alert(self, alert_id: int) -> bool:
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE site_alerts SET resolved = 1 WHERE id = %s", (alert_id,))
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            return False
