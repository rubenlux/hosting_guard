"""Syncs system_alert_events → system_incidents (source_type='system')."""
import json
import logging
from .incident_deduper import _normalize_severity, _query, _resolve_incident, _upsert_incident

logger = logging.getLogger(__name__)


def sync_system_alerts(conn) -> dict:
    counts: dict = {"created": 0, "updated": 0, "resolved": 0}

    try:
        open_rows = _query(
            conn,
            """
            SELECT id, alert_name, severity, component, message, labels, fired_at
              FROM system_alert_events
             WHERE resolved_at IS NULL
            """,
        )
    except Exception as exc:
        logger.warning("sync_incidents_feed: system_alert_events query failed: %s", exc)
        return counts

    seen_keys: set = set()
    for row in open_rows:
        key = f"system_alert:{row['alert_name']}"
        seen_keys.add(key)

        fired_at = row["fired_at"]
        evidence: dict = {
            "source": "system_alert_events",
            "alert_id": row["id"],
            "alert_name": row["alert_name"],
            "component": row["component"],
            "message": row["message"],
            "fired_at": fired_at.isoformat() if hasattr(fired_at, "isoformat") else str(fired_at),
        }
        raw_labels = row.get("labels")
        if raw_labels:
            try:
                evidence["labels"] = (
                    json.loads(raw_labels) if isinstance(raw_labels, str) else raw_labels
                )
            except Exception:
                pass

        component = row["component"].upper()
        result = _upsert_incident(
            conn,
            source_table="system_alert_events",
            source_id=str(row["id"]),
            source_type="system",
            correlation_key=key,
            incident_type=row["alert_name"].lower(),
            severity=_normalize_severity(row["severity"]),
            hosting_id=None,
            user_id=None,
            title=f"[{component}] {row['alert_name']}: {row['message']}",
            summary=row["message"],
            evidence=evidence,
        )
        counts[result] += 1

    open_incidents = _query(
        conn,
        "SELECT correlation_key FROM system_incidents"
        " WHERE source_type = 'system' AND status = 'open'",
    )
    for inc in open_incidents:
        if inc["correlation_key"] not in seen_keys:
            if _resolve_incident(conn, inc["correlation_key"]):
                counts["resolved"] += 1

    return counts
