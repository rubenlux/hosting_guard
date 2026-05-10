"""Syncs site_alerts → system_incidents (source_type='site')."""
import logging
from .incident_deduper import _normalize_severity, _query, _resolve_incident, _upsert_incident

logger = logging.getLogger(__name__)


def sync_site_alerts(conn) -> dict:
    counts: dict = {"created": 0, "updated": 0, "resolved": 0}

    try:
        open_rows = _query(
            conn,
            """
            SELECT sa.id, sa.user_id, sa.site_id, sa.level, sa.message, sa.created_at,
                   h.name AS hosting_name, h.subdomain
              FROM site_alerts sa
              JOIN hostings h ON h.hosting_id = sa.site_id
             WHERE sa.resolved = 0
               AND h.status IN ('active', 'starting', 'stopped', 'error')
            """,
        )
    except Exception as exc:
        logger.warning("sync_incidents_feed: site_alerts query failed: %s", exc)
        return counts

    seen_keys: set = set()
    for row in open_rows:
        level = row.get("level") or "warning"
        site_id = row["site_id"]
        key = f"site_alert:{site_id}:{level}"
        seen_keys.add(key)

        name = row.get("hosting_name") or f"hosting:{site_id}"
        created_at = row["created_at"]
        evidence: dict = {
            "source": "site_alerts",
            "alert_id": row["id"],
            "level": level,
            "message": row["message"],
            "subdomain": row.get("subdomain"),
            "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at),
        }

        result = _upsert_incident(
            conn,
            source_table="site_alerts",
            source_id=str(row["id"]),
            source_type="site",
            correlation_key=key,
            incident_type=f"site_{level}",
            severity=_normalize_severity(level),
            hosting_id=site_id,
            user_id=row.get("user_id"),
            title=f"{name}: {row['message']}",
            summary=row.get("message"),
            evidence=evidence,
        )
        counts[result] += 1

    try:
        deleted_incidents = _query(
            conn,
            """
            SELECT si.correlation_key
              FROM system_incidents si
              JOIN hostings h ON h.hosting_id = si.hosting_id
             WHERE si.source_type = 'site'
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
    except Exception as exc:
        logger.warning("sync_incidents_feed: site_alerts deleted-hosting cleanup failed: %s", exc)

    open_incidents = _query(
        conn,
        "SELECT correlation_key FROM system_incidents"
        " WHERE source_type = 'site' AND status = 'open'",
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
