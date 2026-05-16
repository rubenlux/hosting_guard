"""
P3B Admin Backup Control Panel — per-hosting policy overrides.

All routes require admin role. All mutations are audited.
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.security import require_role

router = APIRouter(prefix="/admin", tags=["admin-backup"])


# ── Request models ────────────────────────────────────────────────────────────

class BackupPolicyUpdate(BaseModel):
    automatic_backup_enabled: Optional[bool] = None
    manual_backup_enabled: Optional[bool] = None
    backup_frequency: Optional[str] = None      # none | manual | daily
    retention_policy: Optional[str] = None      # latest_only | ttl | manual_limited
    automatic_ttl_hours: Optional[int] = None
    max_manual_backups: Optional[int] = None
    max_backup_storage_mb: Optional[int] = None
    max_total_backup_mb: Optional[int] = None
    admin_override: Optional[bool] = None
    addon_active: Optional[bool] = None
    included_in_plan: Optional[bool] = None
    paused: Optional[bool] = None
    paused_reason: Optional[str] = None
    change_reason: Optional[str] = None


class AdminBackupCreate(BaseModel):
    backup_type: str = "full"   # full | files | database
    reason: Optional[str] = None


class PauseRequest(BaseModel):
    reason: str


class ResumeRequest(BaseModel):
    reason: str


class CleanupRequest(BaseModel):
    mode: str = "all_safe"      # expired | old_manual | automatic_previous | all_safe
    dry_run: bool = True


class RevertRequest(BaseModel):
    history_id: int
    reason: Optional[str] = None


class ProtectRequest(BaseModel):
    protected: bool
    reason: Optional[str] = None


# ── GET effective policy ──────────────────────────────────────────────────────

@router.get("/hostings/{hosting_id}/backup-policy")
def get_backup_policy(
    hosting_id: int,
    admin: dict = Depends(require_role("admin")),
):
    """Return effective backup policy, combining plan + policy table."""
    from app.services.backup_policy_service import get_effective_policy, effective_policy_to_dict
    try:
        policy = get_effective_policy(hosting_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return effective_policy_to_dict(policy)


# ── PUT update policy ─────────────────────────────────────────────────────────

@router.put("/hostings/{hosting_id}/backup-policy")
def update_backup_policy(
    hosting_id: int,
    body: BackupPolicyUpdate,
    admin: dict = Depends(require_role("admin")),
):
    """Create or update the policy row for a hosting."""
    from app.services.backup_policy_service import upsert_policy
    try:
        result = upsert_policy(
            hosting_id,
            admin["user_id"],
            automatic_backup_enabled=body.automatic_backup_enabled,
            manual_backup_enabled=body.manual_backup_enabled,
            backup_frequency=body.backup_frequency,
            retention_policy=body.retention_policy,
            automatic_ttl_hours=body.automatic_ttl_hours,
            max_manual_backups=body.max_manual_backups,
            max_backup_storage_mb=body.max_backup_storage_mb,
            max_total_backup_mb=body.max_total_backup_mb,
            admin_override=body.admin_override,
            addon_active=body.addon_active,
            included_in_plan=body.included_in_plan,
            paused=body.paused,
            paused_reason=body.paused_reason,
            reason=body.change_reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return result


# ── POST admin-forced manual backup ──────────────────────────────────────────

@router.post("/hostings/{hosting_id}/backups")
def admin_create_backup(
    hosting_id: int,
    body: AdminBackupCreate,
    admin: dict = Depends(require_role("admin")),
):
    """
    Force a manual backup for any hosting, bypassing plan restrictions.
    Allowed even if paused (admin override).
    """
    from app.services.tenant_backup_service import create_tenant_backup
    from app.services.activity_service import log_event

    try:
        log_event(
            user_id=admin["user_id"],
            hosting_id=hosting_id,
            actor_type="admin",
            event_type="backup.admin.manual_backup_started",
            category="backup",
            severity="info",
            title="admin manual backup started",
            metadata={"backup_type": body.backup_type, "reason": body.reason},
        )
    except Exception:
        pass

    result = create_tenant_backup(
        hosting_id,
        backup_type=body.backup_type,
        trigger="manual",
        admin_override=True,
        requested_by_user_id=admin["user_id"],
    )

    if result.get("status") == "failed":
        raise HTTPException(
            status_code=500,
            detail=result.get("error_message") or str(result.get("error_code", "backup_failed")),
        )
    return result


# ── GET admin backup list ─────────────────────────────────────────────────────

@router.get("/hostings/{hosting_id}/backups")
def admin_list_backups(
    hosting_id: int,
    limit: int = 20,
    admin: dict = Depends(require_role("admin")),
):
    """List all backups for any hosting (admin only). Returns 200 [] when empty."""
    from app.services.tenant_backup_service import list_tenant_backups as _list
    from app.infra.audit.hosting_repository import HostingRepository
    repo = HostingRepository()
    if not repo.get_hosting_any(hosting_id):
        raise HTTPException(status_code=404, detail="Hosting not found")
    try:
        items = _list(hosting_id, admin=True, limit=limit)
    except Exception:
        items = []
    return {"items": items, "total": len(items)}


# ── POST pause ────────────────────────────────────────────────────────────────

@router.post("/hostings/{hosting_id}/backups/pause")
def pause_backups(
    hosting_id: int,
    body: PauseRequest,
    admin: dict = Depends(require_role("admin")),
):
    """Pause automatic backups for a hosting (manual still allowed for admin)."""
    from app.services.backup_policy_service import upsert_policy
    try:
        result = upsert_policy(
            hosting_id,
            admin["user_id"],
            paused=True,
            paused_reason=body.reason,
            reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"status": "paused", "paused_reason": body.reason, "policy": result}


# ── POST resume ───────────────────────────────────────────────────────────────

@router.post("/hostings/{hosting_id}/backups/resume")
def resume_backups(
    hosting_id: int,
    body: ResumeRequest,
    admin: dict = Depends(require_role("admin")),
):
    """Resume automatic backups after a pause."""
    from app.services.backup_policy_service import upsert_policy
    try:
        result = upsert_policy(
            hosting_id,
            admin["user_id"],
            paused=False,
            paused_reason=None,
            reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"status": "resumed", "policy": result}


# ── POST cleanup ──────────────────────────────────────────────────────────────

@router.post("/hostings/{hosting_id}/backups/cleanup")
def admin_cleanup(
    hosting_id: int,
    body: CleanupRequest,
    admin: dict = Depends(require_role("admin")),
):
    """
    Run cleanup for a specific hosting.
    dry_run=true (default) shows what would be deleted without removing anything.
    """
    from app.services.tenant_backup_service import (
        _cleanup_automatic_previous, _cleanup_manual_excess,
        _cleanup_expired_ttl, list_tenant_backups,
    )
    from app.services.activity_service import log_event

    mode = body.mode
    dry_run = body.dry_run
    affected_ids: list[int] = []
    detail: dict = {}

    try:
        if mode in ("expired", "all_safe"):
            if not dry_run:
                n = _cleanup_expired_ttl()
                detail["expired_deleted"] = n
            else:
                detail["expired_would_delete"] = "use dry_run=false to apply"

        if mode in ("automatic_previous", "all_safe"):
            if not dry_run:
                n = _cleanup_automatic_previous(hosting_id, None)
                detail["automatic_previous_deleted"] = n
            else:
                backups = list_tenant_backups(hosting_id, admin=True)
                auto_completed = [
                    b for b in backups
                    if b.get("trigger") == "schedule"
                    and b.get("status") == "completed"
                    and not b.get("protected")
                ]
                # latest stays, rest would be deleted
                detail["automatic_previous_would_delete"] = max(0, len(auto_completed) - 1)

        if mode in ("old_manual", "all_safe"):
            from app.services.backup_policy_service import get_effective_policy
            policy = get_effective_policy(hosting_id)
            max_m = policy.max_manual_backups
            if not dry_run:
                n = _cleanup_manual_excess(hosting_id, max_m)
                detail["manual_excess_deleted"] = n
            else:
                backups = list_tenant_backups(hosting_id, admin=True)
                manual = [
                    b for b in backups
                    if b.get("trigger") == "manual"
                    and b.get("status") == "completed"
                    and not b.get("protected")
                ]
                detail["manual_excess_would_delete"] = max(0, len(manual) - max_m)

    except Exception as exc:
        try:
            log_event(
                user_id=admin["user_id"],
                hosting_id=hosting_id,
                actor_type="admin",
                event_type="backup.admin.cleanup_failed",
                category="backup",
                severity="warning",
                title="admin cleanup failed",
                metadata={"mode": mode, "dry_run": dry_run, "error": str(exc)},
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(exc))

    try:
        log_event(
            user_id=admin["user_id"],
            hosting_id=hosting_id,
            actor_type="admin",
            event_type="backup.admin.cleanup_completed" if not dry_run else "backup.admin.cleanup_started",
            category="backup",
            severity="info",
            title="admin cleanup",
            metadata={"mode": mode, "dry_run": dry_run, "detail": detail},
        )
    except Exception:
        pass

    return {"dry_run": dry_run, "mode": mode, "detail": detail}


# ── GET policy history ────────────────────────────────────────────────────────

@router.get("/hostings/{hosting_id}/backup-policy/history")
def get_policy_history(
    hosting_id: int,
    limit: int = 50,
    admin: dict = Depends(require_role("admin")),
):
    from app.services.backup_policy_service import get_policy_history
    return get_policy_history(hosting_id, limit=limit)


# ── POST revert policy ────────────────────────────────────────────────────────

@router.post("/hostings/{hosting_id}/backup-policy/revert")
def revert_policy(
    hosting_id: int,
    body: RevertRequest,
    admin: dict = Depends(require_role("admin")),
):
    """Revert policy to a previous history snapshot (creates new history entry)."""
    from app.services.backup_policy_service import revert_policy as _revert
    try:
        result = _revert(hosting_id, body.history_id, admin["user_id"], body.reason)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return result


# ── PATCH protect/unprotect a backup ─────────────────────────────────────────

@router.patch("/hostings/{hosting_id}/backups/{backup_id}/protect")
def set_protected(
    hosting_id: int,
    backup_id: int,
    body: ProtectRequest,
    admin: dict = Depends(require_role("admin")),
):
    """Mark or unmark a specific backup as protected (immune to cleanup)."""
    from app.services.backup_policy_service import set_backup_protected
    ok = set_backup_protected(backup_id, body.protected, admin["user_id"], body.reason)
    if not ok:
        raise HTTPException(status_code=404, detail=f"backup_id {backup_id} not found")
    return {"backup_id": backup_id, "protected": body.protected}
