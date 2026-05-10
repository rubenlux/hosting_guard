"""Syncs security_events → system_incidents (source_type='security')."""
import logging
from .incident_deduper import _normalize_severity, _query, _resolve_incident, _upsert_incident

logger = logging.getLogger(__name__)


def sync_security_events(conn) -> dict:
    counts: dict = {"created": 0, "updated": 0, "resolved": 0}

    open_rows = _query(
        conn,
        """
        SELECT se.event_id, se.user_id, se.hosting_id, se.severity, se.event_type,
               se.title, se.message, se.ip, se.metadata, se.count, se.last_seen
          FROM security_events se
          LEFT JOIN hostings h ON h.hosting_id = se.hosting_id
         WHERE se.status = 'open'
           AND (se.hosting_id IS NULL OR h.status NOT IN ('deleted'))
        """,
    )

    seen_keys: set = set()
    for row in open_rows:
        hid = row.get("hosting_id")
        key = f"security:{row['event_type']}:hosting:{hid if hid is not None else 'global'}"
        seen_keys.add(key)

        last_seen = row["last_seen"]
        evidence: dict = {
            "source": "security_events",
            "event_id": row["event_id"],
            "event_type": row["event_type"],
            "ip": row.get("ip"),
            "count": row["count"],
            "last_seen": last_seen.isoformat() if hasattr(last_seen, "isoformat") else str(last_seen),
        }
        if row.get("metadata"):
            evidence["metadata"] = row["metadata"]

        result = _upsert_incident(
            conn,
            source_table="security_events",
            source_id=str(row["event_id"]),
            source_type="security",
            correlation_key=key,
            incident_type=row["event_type"].lower(),
            severity=_normalize_severity(row["severity"]),
            hosting_id=hid,
            user_id=row.get("user_id"),
            title=row["title"],
            summary=row.get("message"),
            evidence=evidence,
        )
        counts[result] += 1

    deleted_incidents = _query(
        conn,
        """
        SELECT si.correlation_key
          FROM system_incidents si
          JOIN hostings h ON h.hosting_id = si.hosting_id
         WHERE si.source_type = 'security'
           AND si.status = 'open'
           AND h.status = 'deleted'
        """,
    )
    for inc in deleted_incidents:
        if _resolve_incident(
            conn,
            inc["correlation_key"],
            {"resolved_reason": "hosting_deleted", "resolved_by": "sync_incidents_feed"},
        ):
            counts["resolved"] += 1

    open_incidents = _query(
        conn,
        "SELECT correlation_key FROM system_incidents"
        " WHERE source_type = 'security' AND status = 'open'",
    )
    for inc in open_incidents:
        if inc["correlation_key"] not in seen_keys:
            if _resolve_incident(
                conn,
                inc["correlation_key"],
                {"resolved_by": "sync_incidents_feed", "source_status": "not_in_open_set"},
            ):
                counts["resolved"] += 1

    return counts
