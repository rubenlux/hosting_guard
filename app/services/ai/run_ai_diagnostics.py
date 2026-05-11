"""
run_ai_diagnostics — periodic job that generates AI diagnoses for open incidents.

Selects incidents needing diagnosis, builds context, calls Claude (or rule-based
fallback), and saves results to ai_diagnosis. Idempotent via context_hash.

Returns {processed, created, updated, skipped, failed}.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_MIN_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "warning": 3, "info": 4}
_SKIP_SEVERITY = frozenset({"info"})


def _fetch_open_incidents(conn, limit: int) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT incident_id, source_type, incident_type, severity,
               title, summary, evidence, count, hosting_id, user_id,
               first_seen, last_seen, updated_at
          FROM system_incidents
         WHERE status = 'open'
           AND severity != 'info'
         ORDER BY
           CASE severity
             WHEN 'critical' THEN 0 WHEN 'high' THEN 1
             WHEN 'medium'   THEN 2 WHEN 'warning' THEN 3
             ELSE 4
           END,
           last_seen DESC
         LIMIT %s
        """,
        (limit,),
    )
    return [dict(r) for r in cur.fetchall()]


def _get_existing_diagnosis(conn, incident_id: int) -> Optional[dict]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, context_hash, status
          FROM ai_diagnosis
         WHERE incident_id = %s
         ORDER BY created_at DESC
         LIMIT 1
        """,
        (incident_id,),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _needs_diagnosis(existing: Optional[dict], new_hash: str) -> Optional[str]:
    """
    Returns:
      None     — no existing diagnosis → create
      "skip"   — same hash → skip
      "update" — hash changed → update
    """
    if not existing:
        return None
    if existing.get("context_hash") == new_hash:
        return "skip"
    return "update"


def _save_diagnosis(
    conn,
    *,
    incident: dict,
    diagnosis: dict,
    model: str,
    context_hash: str,
    existing_id: Optional[int],
    prompt_version: str,
) -> str:
    cur = conn.cursor()
    now = datetime.now(timezone.utc)

    severity     = diagnosis.get("severity") or incident.get("severity")
    summary      = diagnosis.get("summary", "")
    root_cause   = diagnosis.get("root_cause", "")
    rec_steps    = diagnosis.get("recommended_next_steps", [])
    cust_msg     = diagnosis.get("customer_message", "")
    admin_notes  = diagnosis.get("admin_notes", "")
    confidence   = diagnosis.get("confidence", 0.5)
    source       = diagnosis.get("diagnosis_source", "llm")

    if existing_id:
        cur.execute(
            """
            UPDATE ai_diagnosis
               SET severity = %s, summary = %s, root_cause = %s,
                   recommended_next_steps = %s::jsonb,
                   customer_message = %s, admin_notes = %s,
                   confidence = %s, context_hash = %s, status = 'active',
                   model = %s, prompt_version = %s,
                   error_message = NULL, updated_at = %s,
                   fingerprint = %s
             WHERE id = %s
            """,
            (
                severity, summary, root_cause,
                json.dumps(rec_steps, ensure_ascii=False),
                cust_msg, admin_notes,
                confidence, context_hash, model, prompt_version,
                now, source, existing_id,
            ),
        )
        return "updated"

    cur.execute(
        """
        INSERT INTO ai_diagnosis
            (incident_id, source_type, incident_type, hosting_id, user_id,
             severity, summary, root_cause,
             recommended_next_steps, customer_message, admin_notes,
             confidence, context_hash, status,
             model, prompt_version, fingerprint,
             created_at, updated_at)
        VALUES
            (%s, %s, %s, %s, %s,
             %s, %s, %s,
             %s::jsonb, %s, %s,
             %s, %s, 'active',
             %s, %s, %s,
             %s, %s)
        """,
        (
            incident["incident_id"],
            incident.get("source_type"),
            incident.get("incident_type"),
            incident.get("hosting_id"),
            incident.get("user_id"),
            severity, summary, root_cause,
            json.dumps(rec_steps, ensure_ascii=False),
            cust_msg, admin_notes,
            confidence, context_hash,
            model, prompt_version, source,
            now, now,
        ),
    )
    return "created"


def _save_error(conn, *, incident_id: int, error_message: str, existing_id: Optional[int]) -> None:
    cur = conn.cursor()
    now = datetime.now(timezone.utc)
    if existing_id:
        cur.execute(
            "UPDATE ai_diagnosis SET status = 'error', error_message = %s, updated_at = %s WHERE id = %s",
            (error_message[:500], now, existing_id),
        )
    else:
        cur.execute(
            """
            INSERT INTO ai_diagnosis (incident_id, status, error_message, created_at, updated_at)
            VALUES (%s, 'error', %s, %s, %s)
            """,
            (incident_id, error_message[:500], now, now),
        )


def run_ai_diagnostics(conn=None, limit: int = 10) -> dict:
    """
    Run AI diagnostics for up to `limit` open incidents.

    If conn is None, acquires and releases its own connection.
    Returns {processed, created, updated, skipped, failed}.
    """
    from app.services.ai.diagnostic_context import build_incident_context, compute_context_hash
    from app.services.ai.llm_client import generate_diagnosis, AI_DIAGNOSTIC_PROMPT_VERSION

    _own_conn = conn is None
    if _own_conn:
        from app.infra.db import get_connection, release_connection
        conn = get_connection()

    counts = {"processed": 0, "created": 0, "updated": 0, "skipped": 0, "failed": 0}

    try:
        incidents = _fetch_open_incidents(conn, limit)
        counts["processed"] = len(incidents)

        for incident in incidents:
            incident_id = incident["incident_id"]
            try:
                context = build_incident_context(conn, incident)
                new_hash = compute_context_hash(incident)
                existing = _get_existing_diagnosis(conn, incident_id)
                action = _needs_diagnosis(existing, new_hash)

                if action == "skip":
                    counts["skipped"] += 1
                    continue

                diagnosis, model = generate_diagnosis(context)
                existing_id = existing["id"] if existing else None
                result = _save_diagnosis(
                    conn,
                    incident=incident,
                    diagnosis=diagnosis,
                    model=model,
                    context_hash=new_hash,
                    existing_id=existing_id,
                    prompt_version=AI_DIAGNOSTIC_PROMPT_VERSION,
                )
                conn.commit()
                counts[result] += 1

            except Exception as exc:
                logger.warning("run_ai_diagnostics: failed for incident %s: %s", incident_id, exc)
                try:
                    existing = _get_existing_diagnosis(conn, incident_id)
                    existing_id = existing["id"] if existing else None
                    _save_error(conn, incident_id=incident_id, error_message=str(exc), existing_id=existing_id)
                    conn.commit()
                except Exception:
                    conn.rollback()
                counts["failed"] += 1

        return counts

    except Exception as exc:
        logger.error("run_ai_diagnostics: outer error: %s", exc)
        try:
            conn.rollback()
        except Exception:
            pass
        return counts
    finally:
        if _own_conn:
            release_connection(conn)
