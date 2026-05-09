"""
AI Eyes Layer — Phase 1: Incident Feed Bridge

Syncs open alerts from existing detection tables into system_incidents
as a unified incident feed for AI diagnosis.

Sources:
  security_events     → source_type='security'
  site_alerts         → source_type='site'
  system_alert_events → source_type='system'

Dedup strategy:
  Unique partial index uix_system_incidents_open on (correlation_key)
  WHERE status='open' prevents duplicates. Each run does UPDATE-first,
  INSERT-if-not-found. Severity only ever escalates.

Resolve strategy:
  If a source record disappears from the open set, the corresponding
  system_incident is marked resolved. Re-fires create a new incident.

This job is ADDITIVE — it never modifies any source table.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Severity normalization ────────────────────────────────────────────────────

_SEV_RANK: dict = {"critical": 4, "high": 3, "medium": 2, "warning": 1, "info": 0}


def _normalize_severity(raw: Optional[str]) -> str:
    if not raw:
        return "info"
    s = raw.lower().strip()
    if s in _SEV_RANK:
        return s
    if s == "warn":
        return "warning"
    return "info"


def _sev_rank(sev: str) -> int:
    return _SEV_RANK.get(sev, 0)


# ── DB helpers ────────────────────────────────────────────────────────────────

def _query(conn, sql: str, params: tuple = ()) -> list:
    cur = conn.cursor()
    cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


# ── Core upsert/resolve ───────────────────────────────────────────────────────

def _upsert_incident(
    conn,
    *,
    source_table: str,
    source_id: str,
    source_type: str,
    correlation_key: str,
    incident_type: str,
    severity: str,
    hosting_id: Optional[int],
    user_id: Optional[int],
    title: str,
    summary: Optional[str],
    evidence: dict,
) -> str:
    """
    UPDATE existing open incident or INSERT a new one.
    Severity only escalates (never de-escalates on update).
    Returns 'updated' | 'created'.
    """
    now = datetime.now(timezone.utc)
    evidence_json = json.dumps(evidence)
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE system_incidents
           SET last_seen  = %s,
               count      = count + 1,
               evidence   = %s,
               updated_at = %s,
               severity   = CASE
                   WHEN (CASE severity
                         WHEN 'critical' THEN 4 WHEN 'high'    THEN 3
                         WHEN 'medium'   THEN 2 WHEN 'warning' THEN 1
                         ELSE 0 END) < %s
                   THEN %s ELSE severity END
         WHERE correlation_key = %s AND status = 'open'
        """,
        (now, evidence_json, now, _sev_rank(severity), severity, correlation_key),
    )
    if cur.rowcount > 0:
        return "updated"

    cur.execute(
        """
        INSERT INTO system_incidents
            (source_table, source_id, source_type, correlation_key,
             incident_type, severity, status, hosting_id, user_id,
             title, summary, evidence, count,
             first_seen, last_seen, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, 'open', %s, %s, %s, %s, %s, 1,
                %s, %s, %s, %s)
        ON CONFLICT (correlation_key) WHERE status = 'open' DO NOTHING
        """,
        (
            source_table, source_id, source_type, correlation_key,
            incident_type, severity, hosting_id, user_id,
            title, summary, evidence_json,
            now, now, now, now,
        ),
    )
    return "created"


def _resolve_incident(conn, correlation_key: str) -> bool:
    """Mark open incident as resolved. Returns True if a row was changed."""
    now = datetime.now(timezone.utc)
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE system_incidents
           SET status = 'resolved', resolved_at = %s, updated_at = %s
         WHERE correlation_key = %s AND status = 'open'
        """,
        (now, now, correlation_key),
    )
    return cur.rowcount > 0


# ── Source A: security_events ─────────────────────────────────────────────────

def _sync_security_events(conn) -> dict:
    counts: dict = {"created": 0, "updated": 0, "resolved": 0}

    open_rows = _query(
        conn,
        """
        SELECT event_id, user_id, hosting_id, severity, event_type, title,
               message, ip, metadata, count, last_seen
          FROM security_events
         WHERE status = 'open'
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

    open_incidents = _query(
        conn,
        "SELECT correlation_key FROM system_incidents"
        " WHERE source_type = 'security' AND status = 'open'",
    )
    for inc in open_incidents:
        if inc["correlation_key"] not in seen_keys:
            if _resolve_incident(conn, inc["correlation_key"]):
                counts["resolved"] += 1

    return counts


# ── Source B: site_alerts ─────────────────────────────────────────────────────

def _sync_site_alerts(conn) -> dict:
    counts: dict = {"created": 0, "updated": 0, "resolved": 0}

    try:
        open_rows = _query(
            conn,
            """
            SELECT sa.id, sa.user_id, sa.site_id, sa.level, sa.message, sa.created_at,
                   h.name AS hosting_name, h.subdomain
              FROM site_alerts sa
              LEFT JOIN hostings h ON h.hosting_id = sa.site_id
             WHERE sa.resolved = 0
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

    open_incidents = _query(
        conn,
        "SELECT correlation_key FROM system_incidents"
        " WHERE source_type = 'site' AND status = 'open'",
    )
    for inc in open_incidents:
        if inc["correlation_key"] not in seen_keys:
            if _resolve_incident(conn, inc["correlation_key"]):
                counts["resolved"] += 1

    return counts


# ── Source C: system_alert_events ─────────────────────────────────────────────

def _sync_system_alerts(conn) -> dict:
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


# ── Entry point ───────────────────────────────────────────────────────────────

def sync_incidents_feed() -> None:
    """Called by scheduler every 120 s. Syncs all sources into system_incidents."""
    from app.infra.db import get_connection, release_connection

    conn = None
    try:
        conn = get_connection()
        totals: dict = {"created": 0, "updated": 0, "resolved": 0}

        for label, fn in (
            ("security_events", _sync_security_events),
            ("site_alerts",     _sync_site_alerts),
            ("system_alerts",   _sync_system_alerts),
        ):
            try:
                counts = fn(conn)
                conn.commit()
                for k in totals:
                    totals[k] += counts.get(k, 0)
                logger.debug("sync_incidents_feed[%s]: %s", label, counts)
            except Exception as exc:
                conn.rollback()
                logger.error(
                    "sync_incidents_feed[%s] failed: %s", label, exc, exc_info=True
                )

        if any(totals.values()):
            logger.info(
                "sync_incidents_feed: created=%d updated=%d resolved=%d",
                totals["created"], totals["updated"], totals["resolved"],
            )

    except Exception as exc:
        logger.exception("sync_incidents_feed: unexpected error: %s", exc)
    finally:
        if conn:
            release_connection(conn)
