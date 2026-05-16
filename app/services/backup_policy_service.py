"""
P3B Backup Policy Service — admin-controlled per-hosting backup policies.

Priority (highest wins):
  1. paused=true          → blocks automatic; admin can still force manual
  2. admin_override=true  → allows regardless of plan
  3. addon_active=true    → adds automatic when plan doesn't include it
  4. included_in_plan     → plan-derived defaults
  5. no policy row        → falls back to plan entitlement from users table

Policy changes are immutable-append to tenant_backup_policy_history.
Rollback creates a new history entry, never deletes old ones.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── DB helpers (patchable in tests) ──────────────────────────────────────────

def _get_conn():
    from app.infra.db import get_connection
    return get_connection()


def _rel(conn):
    from app.infra.db import release_connection
    release_connection(conn)


def _audit(event_type: str, hosting_id: Optional[int] = None,
           user_id: Optional[int] = None, metadata: Optional[dict] = None) -> None:
    try:
        from app.services.activity_service import log_event
        log_event(
            user_id=user_id,
            hosting_id=hosting_id,
            actor_type="admin",
            event_type=event_type,
            category="backup",
            severity="info",
            title=event_type.replace(".", " ").replace("_", " "),
            metadata=metadata or {},
        )
    except Exception as exc:
        logger.warning("backup policy audit log failed (%s): %s", event_type, exc)


# ── Effective policy dataclass ────────────────────────────────────────────────

@dataclass
class EffectiveBackupPolicy:
    hosting_id: int
    user_id: int
    plan: str
    automatic_backup_enabled: bool
    manual_backup_enabled: bool
    backup_frequency: str          # none | manual | daily
    retention_policy: str          # latest_only | ttl | manual_limited
    automatic_ttl_hours: int
    max_manual_backups: int
    max_backup_storage_mb: int
    max_total_backup_mb: int
    admin_override: bool
    addon_active: bool
    included_in_plan: bool
    paused: bool
    paused_reason: Optional[str]
    policy_id: Optional[int]       # None when using plan defaults
    source: str                    # "admin_override" | "addon" | "plan" | "default"


# ── Plan entitlement fallback (mirrors tenant_backup_service) ─────────────────

_AUTOMATIC_PLANS = {"agencia_pro", "enterprise", "enterprise_annual", "enterprise_monthly"}
_MANUAL_PLANS = {"negocio", "agencia", "agencia_pro", "enterprise", "enterprise_annual", "enterprise_monthly"}
_MAX_MANUAL: dict[str, int] = {
    "free": 0, "personal": 0, "negocio": 1, "agencia": 2,
    "agencia_pro": 2, "enterprise": 2, "enterprise_annual": 2, "enterprise_monthly": 2,
}


def _plan_defaults(hosting_id: int, user_id: int, plan: str) -> EffectiveBackupPolicy:
    """Build EffectiveBackupPolicy from plan when no policy row exists."""
    manual = plan in _MANUAL_PLANS
    auto = plan in _AUTOMATIC_PLANS
    return EffectiveBackupPolicy(
        hosting_id=hosting_id,
        user_id=user_id,
        plan=plan,
        automatic_backup_enabled=auto,
        manual_backup_enabled=manual,
        backup_frequency="daily" if auto else ("manual" if manual else "none"),
        retention_policy="latest_only" if auto else "manual_limited",
        automatic_ttl_hours=24,
        max_manual_backups=_MAX_MANUAL.get(plan, 0),
        max_backup_storage_mb=2048,
        max_total_backup_mb=2048,
        admin_override=False,
        addon_active=False,
        included_in_plan=manual or auto,
        paused=False,
        paused_reason=None,
        policy_id=None,
        source="plan",
    )


# ── Core policy functions ─────────────────────────────────────────────────────

def get_effective_policy(hosting_id: int) -> EffectiveBackupPolicy:
    """
    Resolve the effective backup policy for a hosting.
    Checks tenant_backup_policies first; falls back to plan entitlement.
    """
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT h.user_id, u.plan,
                      p.policy_id, p.automatic_backup_enabled, p.manual_backup_enabled,
                      p.backup_frequency, p.retention_policy, p.automatic_ttl_hours,
                      p.max_manual_backups, p.max_backup_storage_mb, p.max_total_backup_mb,
                      p.admin_override, p.addon_active, p.included_in_plan,
                      p.paused, p.paused_reason
               FROM hostings h
               JOIN users u ON u.user_id = h.user_id
               LEFT JOIN tenant_backup_policies p ON p.hosting_id = h.hosting_id
               WHERE h.hosting_id = %s""",
            (hosting_id,),
        )
        row = cur.fetchone()
    finally:
        _rel(conn)

    if not row:
        raise ValueError(f"hosting_id {hosting_id} not found")

    row = dict(row)
    user_id = row["user_id"]
    plan = row.get("plan") or "free"

    if row.get("policy_id") is None:
        return _plan_defaults(hosting_id, user_id, plan)

    # Policy row exists — compute effective values
    admin_override = bool(row["admin_override"])
    addon_active = bool(row["addon_active"])
    included_in_plan = bool(row["included_in_plan"])
    paused = bool(row["paused"])

    if admin_override:
        source = "admin_override"
    elif addon_active:
        source = "addon"
    elif included_in_plan:
        source = "plan"
    else:
        source = "default"

    return EffectiveBackupPolicy(
        hosting_id=hosting_id,
        user_id=user_id,
        plan=plan,
        automatic_backup_enabled=bool(row["automatic_backup_enabled"]),
        manual_backup_enabled=bool(row["manual_backup_enabled"]),
        backup_frequency=row["backup_frequency"] or "none",
        retention_policy=row["retention_policy"] or "manual_limited",
        automatic_ttl_hours=int(row["automatic_ttl_hours"] or 24),
        max_manual_backups=int(row["max_manual_backups"] or 2),
        max_backup_storage_mb=int(row["max_backup_storage_mb"] or 2048),
        max_total_backup_mb=int(row["max_total_backup_mb"] or 2048),
        admin_override=admin_override,
        addon_active=addon_active,
        included_in_plan=included_in_plan,
        paused=paused,
        paused_reason=row.get("paused_reason"),
        policy_id=int(row["policy_id"]),
        source=source,
    )


def get_policy_row(hosting_id: int) -> Optional[dict]:
    """Fetch the raw tenant_backup_policies row, or None if not set."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM tenant_backup_policies WHERE hosting_id=%s", (hosting_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        _rel(conn)


def _row_to_dict(row: dict) -> dict:
    """Serialise policy row for JSON history snapshot (drop non-JSON types)."""
    out = {}
    for k, v in row.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _record_history(policy_id: int, hosting_id: int,
                    old_row: Optional[dict], new_row: dict,
                    changed_by: Optional[int], reason: Optional[str]) -> int:
    old_json = json.dumps(_row_to_dict(old_row) if old_row else {})
    new_json = json.dumps(_row_to_dict(new_row))
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO tenant_backup_policy_history
               (policy_id, hosting_id, previous_policy_json, new_policy_json,
                changed_by_user_id, change_reason)
               VALUES (%s, %s, %s, %s, %s, %s)
               RETURNING history_id""",
            (policy_id, hosting_id, old_json, new_json, changed_by, reason),
        )
        row = cur.fetchone()
        conn.commit()
        return int(dict(row)["history_id"])
    except Exception:
        conn.rollback()
        raise
    finally:
        _rel(conn)


def upsert_policy(
    hosting_id: int,
    admin_user_id: int,
    *,
    automatic_backup_enabled: Optional[bool] = None,
    manual_backup_enabled: Optional[bool] = None,
    backup_frequency: Optional[str] = None,
    retention_policy: Optional[str] = None,
    automatic_ttl_hours: Optional[int] = None,
    max_manual_backups: Optional[int] = None,
    max_backup_storage_mb: Optional[int] = None,
    max_total_backup_mb: Optional[int] = None,
    admin_override: Optional[bool] = None,
    addon_active: Optional[bool] = None,
    included_in_plan: Optional[bool] = None,
    paused: Optional[bool] = None,
    paused_reason: Optional[str] = None,
    reason: Optional[str] = None,
) -> dict:
    """
    Create or update the policy row for a hosting.
    All fields are optional — only provided fields are updated.
    Returns the new effective policy as a dict.
    Each logical read uses its own connection so fake DB helpers in tests work cleanly.
    """
    # ── 1. Fetch hosting (separate conn for test isolation) ───────────────────
    conn_h = _get_conn()
    try:
        cur_h = conn_h.cursor()
        cur_h.execute("SELECT user_id FROM hostings WHERE hosting_id=%s", (hosting_id,))
        h = cur_h.fetchone()
        if not h:
            raise ValueError(f"hosting_id {hosting_id} not found")
        user_id = dict(h)["user_id"]
    finally:
        _rel(conn_h)

    # ── 2. Fetch existing policy row ──────────────────────────────────────────
    conn_p = _get_conn()
    try:
        cur_p = conn_p.cursor()
        cur_p.execute(
            "SELECT * FROM tenant_backup_policies WHERE hosting_id=%s FOR UPDATE",
            (hosting_id,),
        )
        existing = cur_p.fetchone()
        old_row = dict(existing) if existing else None
    finally:
        _rel(conn_p)

    # ── 3. Persist (conn_w opened inside each branch so sequence is predictable) ─
    if existing is None:
        # Need plan to seed defaults — conn order: conn_u then conn_w
        conn_u = _get_conn()
        try:
            cur_u = conn_u.cursor()
            cur_u.execute("SELECT plan FROM users WHERE user_id=%s", (user_id,))
            u = cur_u.fetchone()
            plan = (dict(u).get("plan") or "free") if u else "free"
        finally:
            _rel(conn_u)
        defaults = _plan_defaults(hosting_id, user_id, plan)

        conn_w = _get_conn()
        try:
            cur_w = conn_w.cursor()
            cur_w.execute(
                """INSERT INTO tenant_backup_policies
                   (hosting_id, user_id,
                    automatic_backup_enabled, manual_backup_enabled,
                    backup_frequency, retention_policy, automatic_ttl_hours,
                    max_manual_backups, max_backup_storage_mb, max_total_backup_mb,
                    admin_override, addon_active, included_in_plan,
                    paused, paused_reason, updated_by_user_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING *""",
                (
                    hosting_id, user_id,
                    automatic_backup_enabled if automatic_backup_enabled is not None else defaults.automatic_backup_enabled,
                    manual_backup_enabled if manual_backup_enabled is not None else defaults.manual_backup_enabled,
                    backup_frequency or defaults.backup_frequency,
                    retention_policy or defaults.retention_policy,
                    automatic_ttl_hours if automatic_ttl_hours is not None else defaults.automatic_ttl_hours,
                    max_manual_backups if max_manual_backups is not None else defaults.max_manual_backups,
                    max_backup_storage_mb if max_backup_storage_mb is not None else defaults.max_backup_storage_mb,
                    max_total_backup_mb if max_total_backup_mb is not None else defaults.max_total_backup_mb,
                    admin_override if admin_override is not None else False,
                    addon_active if addon_active is not None else False,
                    included_in_plan if included_in_plan is not None else defaults.included_in_plan,
                    paused if paused is not None else False,
                    paused_reason,
                    admin_user_id,
                ),
            )
            new_row = dict(cur_w.fetchone())
            conn_w.commit()
        except Exception:
            conn_w.rollback()
            raise
        finally:
            _rel(conn_w)
    else:
        ex = old_row
        conn_w = _get_conn()
        try:
            cur_w = conn_w.cursor()
            cur_w.execute(
                """UPDATE tenant_backup_policies SET
                   automatic_backup_enabled = %s,
                   manual_backup_enabled    = %s,
                   backup_frequency         = %s,
                   retention_policy         = %s,
                   automatic_ttl_hours      = %s,
                   max_manual_backups       = %s,
                   max_backup_storage_mb    = %s,
                   max_total_backup_mb      = %s,
                   admin_override           = %s,
                   addon_active             = %s,
                   included_in_plan         = %s,
                   paused                   = %s,
                   paused_reason            = %s,
                   updated_at               = NOW(),
                   updated_by_user_id       = %s
                   WHERE hosting_id = %s
                   RETURNING *""",
                (
                    automatic_backup_enabled if automatic_backup_enabled is not None else ex["automatic_backup_enabled"],
                    manual_backup_enabled if manual_backup_enabled is not None else ex["manual_backup_enabled"],
                    backup_frequency or ex["backup_frequency"],
                    retention_policy or ex["retention_policy"],
                    automatic_ttl_hours if automatic_ttl_hours is not None else ex["automatic_ttl_hours"],
                    max_manual_backups if max_manual_backups is not None else ex["max_manual_backups"],
                    max_backup_storage_mb if max_backup_storage_mb is not None else ex["max_backup_storage_mb"],
                    max_total_backup_mb if max_total_backup_mb is not None else ex["max_total_backup_mb"],
                    admin_override if admin_override is not None else ex["admin_override"],
                    addon_active if addon_active is not None else ex["addon_active"],
                    included_in_plan if included_in_plan is not None else ex["included_in_plan"],
                    paused if paused is not None else ex["paused"],
                    paused_reason if paused_reason is not None else ex.get("paused_reason"),
                    admin_user_id,
                    hosting_id,
                ),
            )
            new_row = dict(cur_w.fetchone())
            conn_w.commit()
        except Exception:
            conn_w.rollback()
            raise
        finally:
            _rel(conn_w)

    policy_id = int(new_row["policy_id"])
    _record_history(policy_id, hosting_id, old_row, new_row, admin_user_id, reason)

    # Determine audit event type
    if old_row is None:
        event = "backup.policy.created"
    elif new_row.get("paused") and not old_row.get("paused"):
        event = "backup.policy.paused"
    elif not new_row.get("paused") and old_row.get("paused"):
        event = "backup.policy.resumed"
    elif new_row.get("admin_override") and not old_row.get("admin_override"):
        event = "backup.policy.admin_override_enabled"
    elif not new_row.get("admin_override") and old_row and old_row.get("admin_override"):
        event = "backup.policy.admin_override_disabled"
    else:
        event = "backup.policy.updated"

    _audit(event, hosting_id=hosting_id, user_id=admin_user_id,
           metadata={"reason": reason, "policy_id": policy_id})

    return _row_to_dict(new_row)


def get_policy_history(hosting_id: int, limit: int = 50) -> list:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT history_id, policy_id, hosting_id,
                      previous_policy_json, new_policy_json,
                      changed_by_user_id, change_reason, created_at
               FROM tenant_backup_policy_history
               WHERE hosting_id = %s
               ORDER BY created_at DESC LIMIT %s""",
            (hosting_id, limit),
        )
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        _rel(conn)

    for r in rows:
        if isinstance(r.get("created_at"), datetime):
            r["created_at"] = r["created_at"].isoformat()
        # previous/new_policy_json are already dicts (JSONB) or strings
        for key in ("previous_policy_json", "new_policy_json"):
            if isinstance(r.get(key), str):
                try:
                    r[key] = json.loads(r[key])
                except (json.JSONDecodeError, TypeError):
                    pass
    return rows


def revert_policy(hosting_id: int, history_id: int, admin_user_id: int,
                  reason: Optional[str] = None) -> dict:
    """
    Revert policy to the state captured in a history snapshot.
    Creates a new history entry — never deletes old ones.
    Rollback only changes future configuration, not existing backups.
    """
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM tenant_backup_policy_history WHERE history_id=%s AND hosting_id=%s",
            (history_id, hosting_id),
        )
        hist = cur.fetchone()
        if not hist:
            raise ValueError(f"history_id {history_id} not found for hosting_id {hosting_id}")
        target_json = dict(hist)["previous_policy_json"]
        if isinstance(target_json, str):
            target_json = json.loads(target_json)
    finally:
        _rel(conn)

    # Apply the snapshot via upsert_policy — only settable fields
    return upsert_policy(
        hosting_id,
        admin_user_id,
        automatic_backup_enabled=target_json.get("automatic_backup_enabled"),
        manual_backup_enabled=target_json.get("manual_backup_enabled"),
        backup_frequency=target_json.get("backup_frequency"),
        retention_policy=target_json.get("retention_policy"),
        automatic_ttl_hours=target_json.get("automatic_ttl_hours"),
        max_manual_backups=target_json.get("max_manual_backups"),
        max_backup_storage_mb=target_json.get("max_backup_storage_mb"),
        max_total_backup_mb=target_json.get("max_total_backup_mb"),
        admin_override=target_json.get("admin_override"),
        addon_active=target_json.get("addon_active"),
        included_in_plan=target_json.get("included_in_plan"),
        paused=target_json.get("paused"),
        paused_reason=target_json.get("paused_reason"),
        reason=reason or f"reverted to history_id={history_id}",
    )


def set_backup_protected(backup_id: int, protected: bool,
                         admin_user_id: int,
                         reason: Optional[str] = None) -> bool:
    """Mark or unmark a backup as protected (safe from cleanup)."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT backup_id, hosting_id, user_id FROM tenant_backups WHERE backup_id=%s",
            (backup_id,),
        )
        row = cur.fetchone()
        if not row:
            return False
        row = dict(row)
        cur.execute(
            "UPDATE tenant_backups SET protected=%s, protected_reason=%s WHERE backup_id=%s",
            (protected, reason, backup_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _rel(conn)

    _audit(
        "backup.admin.protected" if protected else "backup.admin.unprotected",
        hosting_id=row["hosting_id"],
        user_id=admin_user_id,
        metadata={"backup_id": backup_id, "reason": reason},
    )
    return True


def effective_policy_to_dict(p: EffectiveBackupPolicy) -> dict:
    return asdict(p)
