"""
Shared DB helpers for incident upsert/resolve operations.

All sync modules depend on these helpers. The _query / _upsert_incident /
_resolve_incident trio is kept here to avoid duplication across sources.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

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


def _query(conn, sql: str, params: tuple = ()) -> list:
    cur = conn.cursor()
    cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


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


def _resolve_incident(
    conn,
    correlation_key: str,
    extra_evidence: Optional[dict] = None,
) -> bool:
    """Mark open incident as resolved. Returns True if a row was changed."""
    now = datetime.now(timezone.utc)
    cur = conn.cursor()
    if extra_evidence:
        cur.execute(
            """
            UPDATE system_incidents
               SET status = 'resolved', resolved_at = %s, updated_at = %s,
                   evidence = evidence || %s::jsonb
             WHERE correlation_key = %s AND status = 'open'
            """,
            (now, now, json.dumps(extra_evidence), correlation_key),
        )
    else:
        cur.execute(
            """
            UPDATE system_incidents
               SET status = 'resolved', resolved_at = %s, updated_at = %s
             WHERE correlation_key = %s AND status = 'open'
            """,
            (now, now, correlation_key),
        )
    return cur.rowcount > 0
