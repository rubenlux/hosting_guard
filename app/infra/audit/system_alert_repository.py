"""
Repository for system-level alerts persisted by the Prometheus alert poller.

Alerts are written when Prometheus fires them and marked resolved when they
stop firing. The /health/system endpoint reads from this table — the dashboard
shows decisions already made by the observability system, not UI-computed values.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.infra.db import get_connection, release_connection

logger = logging.getLogger(__name__)


class SystemAlertRepository:

    def upsert_firing_alert(
        self,
        alert_name: str,
        severity: str,
        component: str,
        message: str,
        labels: Optional[Dict] = None,
    ) -> None:
        """Insert a new firing alert, or leave it unchanged if already active."""
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO system_alert_events
                   (alert_name, severity, component, message, labels, fired_at)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (alert_name, (resolved_at IS NULL))
                   WHERE resolved_at IS NULL
                   DO NOTHING""",
                (
                    alert_name,
                    severity,
                    component,
                    message,
                    json.dumps(labels or {}),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            logger.error("upsert_firing_alert failed: %s", exc)
        finally:
            release_connection(conn)

    def resolve_alerts_not_in(self, active_alert_names: set) -> int:
        """Mark resolved any active alerts whose name is no longer in the firing set."""
        conn = get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()
            if active_alert_names:
                # Build parameterized NOT IN
                placeholders = ",".join(["%s"] * len(active_alert_names))
                cursor.execute(
                    f"""UPDATE system_alert_events
                        SET resolved_at = %s
                        WHERE resolved_at IS NULL
                          AND alert_name NOT IN ({placeholders})""",
                    (now, *active_alert_names),
                )
            else:
                cursor.execute(
                    "UPDATE system_alert_events SET resolved_at = %s WHERE resolved_at IS NULL",
                    (now,),
                )
            conn.commit()
            return cursor.rowcount
        except Exception as exc:
            conn.rollback()
            logger.error("resolve_alerts_not_in failed: %s", exc)
            return 0
        finally:
            release_connection(conn)

    def get_active_alerts(self) -> List[Dict]:
        """Return all currently firing (unresolved) alerts."""
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM system_alert_events WHERE resolved_at IS NULL ORDER BY fired_at DESC"
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_connection(conn)

    def get_recent_alerts(self, limit: int = 50) -> List[Dict]:
        """Return recent alerts (firing + resolved) for the audit log."""
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM system_alert_events ORDER BY fired_at DESC LIMIT %s",
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_connection(conn)
