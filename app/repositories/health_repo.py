# app/repositories/health_repo.py
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from app.infra.audit.sqlite import get_connection
from app.infra.db import BACKEND

logger = logging.getLogger(__name__)
_PH = "%s" if BACKEND == "postgresql" else "?"

def save_health(data: Dict):
    """
    Guarda una entrada en el histórico de salud.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        p = _PH

        cursor.execute(
            f"""INSERT INTO site_health_history 
               (user_id, site_id, score, status, cpu, ram, error_count, warning_count, created_at)
               VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})""",
            (
                data["user_id"],
                data["site_id"],
                data["score"],
                data["status"],
                data["cpu"],
                data["ram"],
                data["error_count"],
                data["warning_count"],
                now
            )
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to save health history: {e}", exc_info=True)
        try: conn.rollback() 
        except: pass
        return False

def get_history(site_id: int, limit: int = 50) -> List[Dict]:
    """
    Obtiene el historial de salud de un sitio.
    """
    conn = get_connection()
    cursor = conn.cursor()
    p = _PH
    cursor.execute(
        f"""SELECT score, cpu, ram, created_at
            FROM site_health_history 
            WHERE site_id = {p} 
            ORDER BY created_at DESC 
            LIMIT {p}""",
        (site_id, limit)
    )
    rows = cursor.fetchall()
    return [dict(r) for r in rows]

def save_alert(data: Dict):
    """
    Guarda una alerta en la tabla site_alerts.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        p = _PH
        cursor.execute(
            f"INSERT INTO site_alerts (user_id, site_id, level, message, created_at) VALUES ({p}, {p}, {p}, {p}, {p})",
            (data["user_id"], data["site_id"], data["type"], data["message"], now)
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to save alert: {e}", exc_info=True)
        try: conn.rollback()
        except: pass
        return False
