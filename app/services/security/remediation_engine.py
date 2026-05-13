"""
Remediation engine — applies safe, reversible auto-remediations.

Contract:
- Only types in ALLOWED_AUTO_REMEDIATIONS may be applied.
- Policy gate runs before any action; if rejected, row is written with
  status='blocked_by_policy'.
- Every execution (applied OR blocked) writes a row to remediation_executions.
- Cooldown is set in Redis after a successful apply.
- Fallback allow if Redis is unavailable (never blocks legitimate traffic).
- No container restarts, no Docker changes, no client data touched.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.services.security.ip_blocklist import (
    block_ip_for_hosting,
    block_route_for_hosting,
)
from app.services.security.remediation_policy import (
    ALLOWED_AUTO_REMEDIATIONS,
    PolicyDecision,
    evaluate_remediation_policy,
    get_remediation_spec,
    set_cooldown,
)

logger = logging.getLogger(__name__)


def apply_safe_remediation(
    *,
    conn,
    remediation_type: str,
    hosting_id: int,
    rule_id: str,
    target_type: str,
    target_value: str,
    reason: str,
    evidence: dict,
    protection_mode: str,
    incident_id: Optional[int] = None,
    security_event_id: Optional[int] = None,
    action_id: Optional[int] = None,
    plan_id: Optional[int] = None,
    user_id: Optional[int] = None,
    redis_client=None,
) -> dict:
    """Apply a safe auto-remediation.

    Returns a dict with keys: remediation_id, status, reason, remediation_type.
    Always writes a row to remediation_executions regardless of outcome.
    """
    spec = get_remediation_spec(remediation_type)
    if spec is None:
        return _write_blocked(
            conn,
            hosting_id=hosting_id,
            remediation_type=remediation_type,
            rule_id=rule_id,
            target_type=target_type,
            target_value=target_value,
            reason=f"remediation_type '{remediation_type}' not in allowlist",
            evidence=evidence,
            incident_id=incident_id,
            security_event_id=security_event_id,
            user_id=user_id,
        )

    decision: PolicyDecision = evaluate_remediation_policy(
        remediation_type=remediation_type,
        hosting_id=hosting_id,
        rule_id=rule_id,
        target_value=target_value,
        protection_mode=protection_mode,
        redis_client=redis_client,
    )

    if not decision.allowed:
        return _write_blocked(
            conn,
            hosting_id=hosting_id,
            remediation_type=remediation_type,
            rule_id=rule_id,
            target_type=target_type,
            target_value=target_value,
            reason=decision.reason,
            evidence=evidence,
            incident_id=incident_id,
            security_event_id=security_event_id,
            user_id=user_id,
        )

    ttl_seconds: int = spec["ttl_seconds"]
    risk_level: str = spec["risk_level"]
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=ttl_seconds)

    # Apply the block
    applied = _execute_block(
        remediation_type=remediation_type,
        hosting_id=hosting_id,
        target_value=target_value,
        reason=reason,
        rule_id=rule_id,
        ttl_seconds=ttl_seconds,
    )

    status = "applied" if applied else "failed"

    remediation_id = _write_row(
        conn,
        hosting_id=hosting_id,
        user_id=user_id,
        incident_id=incident_id,
        security_event_id=security_event_id,
        action_id=action_id,
        plan_id=plan_id,
        remediation_type=remediation_type,
        rule_id=rule_id,
        target_type=target_type,
        target_value=target_value,
        status=status,
        risk_level=risk_level,
        reversible=spec.get("reversible", True),
        automatic=True,
        ttl_seconds=ttl_seconds,
        expires_at=expires_at,
        reason=reason,
        evidence=evidence,
        decision={"policy": "approved", "mode": protection_mode},
        blocked_by_policy_reason=None,
        created_by="system",
    )

    if applied:
        set_cooldown(
            hosting_id=hosting_id,
            rule_id=rule_id,
            target_value=target_value,
            redis_client=redis_client,
        )
        logger.info(
            "remediation_engine: applied type=%s hosting=%s target=%s ttl=%ds id=%s",
            remediation_type, hosting_id, target_value, ttl_seconds, remediation_id,
        )
    else:
        logger.warning(
            "remediation_engine: block failed type=%s hosting=%s target=%s",
            remediation_type, hosting_id, target_value,
        )

    return {
        "remediation_id": remediation_id,
        "status": status,
        "reason": reason,
        "remediation_type": remediation_type,
    }


def rollback_remediation(*, conn, remediation_id: int) -> dict:
    """Manually roll back an active remediation (clear the Redis block)."""
    import json

    cur = conn.cursor()
    cur.execute(
        """SELECT remediation_id, remediation_type, hosting_id, target_type,
                  target_value, rule_id, status
           FROM remediation_executions
           WHERE remediation_id = %s""",
        (remediation_id,),
    )
    row = cur.fetchone()
    if not row:
        return {"error": "not_found"}

    row = dict(row)
    if row["status"] not in ("applied",):
        return {"error": "not_rollbackable", "status": row["status"]}

    _clear_block(
        remediation_type=row["remediation_type"],
        hosting_id=row["hosting_id"],
        target_value=row["target_value"],
    )

    now = datetime.now(timezone.utc)
    cur.execute(
        """UPDATE remediation_executions
           SET status='rollback_completed', rollback_status='manual', rollback_at=%s, updated_at=%s
           WHERE remediation_id=%s""",
        (now, now, remediation_id),
    )
    conn.commit()
    logger.info("remediation_engine: rolled back remediation_id=%s", remediation_id)
    return {"remediation_id": remediation_id, "status": "rollback_completed"}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _execute_block(
    *,
    remediation_type: str,
    hosting_id: int,
    target_value: str,
    reason: str,
    rule_id: str,
    ttl_seconds: int,
) -> bool:
    if remediation_type in ("temporary_ip_block", "temporary_scanner_block"):
        return block_ip_for_hosting(
            target_value, hosting_id, reason, rule_id, ttl_seconds
        )
    if remediation_type == "temporary_xmlrpc_block":
        return block_route_for_hosting(
            "xmlrpc", hosting_id, reason, rule_id, ttl_seconds
        )
    if remediation_type == "temporary_rate_limit":
        return block_route_for_hosting(
            f"rate_limit:{target_value}", hosting_id, reason, rule_id, ttl_seconds
        )
    return False


def _clear_block(*, remediation_type: str, hosting_id: int, target_value: str) -> None:
    from app.services.security.ip_blocklist import (
        clear_ip_for_hosting,
        clear_route_for_hosting,
    )

    if remediation_type in ("temporary_ip_block", "temporary_scanner_block"):
        clear_ip_for_hosting(target_value, hosting_id)
    elif remediation_type == "temporary_xmlrpc_block":
        clear_route_for_hosting("xmlrpc", hosting_id)
    elif remediation_type == "temporary_rate_limit":
        clear_route_for_hosting(f"rate_limit:{target_value}", hosting_id)


def _write_blocked(
    conn,
    *,
    hosting_id: int,
    remediation_type: str,
    rule_id: str,
    target_type: str,
    target_value: str,
    reason: str,
    evidence: dict,
    incident_id: Optional[int],
    security_event_id: Optional[int],
    user_id: Optional[int],
) -> dict:
    remediation_id = _write_row(
        conn,
        hosting_id=hosting_id,
        user_id=user_id,
        incident_id=incident_id,
        security_event_id=security_event_id,
        action_id=None,
        plan_id=None,
        remediation_type=remediation_type,
        rule_id=rule_id,
        target_type=target_type,
        target_value=target_value,
        status="blocked_by_policy",
        risk_level=None,
        reversible=True,
        automatic=True,
        ttl_seconds=None,
        expires_at=None,
        reason=reason,
        evidence=evidence,
        decision={},
        blocked_by_policy_reason=reason,
        created_by="system",
    )
    logger.info(
        "remediation_engine: blocked_by_policy type=%s hosting=%s reason=%s",
        remediation_type, hosting_id, reason,
    )
    return {
        "remediation_id": remediation_id,
        "status": "blocked_by_policy",
        "reason": reason,
        "remediation_type": remediation_type,
    }


def _write_row(
    conn,
    *,
    hosting_id: int,
    user_id: Optional[int],
    incident_id: Optional[int],
    security_event_id: Optional[int],
    action_id: Optional[int],
    plan_id: Optional[int],
    remediation_type: str,
    rule_id: Optional[str],
    target_type: Optional[str],
    target_value: Optional[str],
    status: str,
    risk_level: Optional[str],
    reversible: bool,
    automatic: bool,
    ttl_seconds: Optional[int],
    expires_at,
    reason: Optional[str],
    evidence: dict,
    decision: dict,
    blocked_by_policy_reason: Optional[str],
    created_by: str,
) -> Optional[int]:
    import json

    cur = conn.cursor()
    cur.execute(
        """INSERT INTO remediation_executions
           (hosting_id, user_id, incident_id, security_event_id, action_id, plan_id,
            remediation_type, rule_id, target_type, target_value, status, risk_level,
            reversible, automatic, ttl_seconds, expires_at, reason, evidence, decision,
            blocked_by_policy_reason, created_by)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           RETURNING remediation_id""",
        (
            hosting_id, user_id, incident_id, security_event_id, action_id, plan_id,
            remediation_type, rule_id, target_type, target_value, status, risk_level,
            reversible, automatic, ttl_seconds, expires_at,
            reason,
            json.dumps(evidence),
            json.dumps(decision),
            blocked_by_policy_reason,
            created_by,
        ),
    )
    row = cur.fetchone()
    conn.commit()
    return dict(row)["remediation_id"] if row else None
