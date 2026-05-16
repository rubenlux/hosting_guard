# TENANT_BACKUP_LOCAL_STORAGE_FULL

**Severity**: high  
**Status**: confirmed  
**auto_repair**: false

## Description

The local backup directory (`/opt/hostingguard-backups`) has insufficient disk
space to complete a backup. New backups fail with `No space left on device`.

## Symptoms

- `backup.tenant.failed` with `error_code=backup_local_storage_full`
- OS error: `OSError: [Errno 28] No space left on device`
- Log: `backup_local_storage_full`
- `df -h /opt/hostingguard-backups` shows 100% or near-100% utilization

## Root Causes

1. Retention cleanup not running — old backups accumulating
2. Tenant sites growing faster than expected
3. `BACKUP_MAX_TOTAL_GB` / `BACKUP_MAX_PER_TENANT_GB` limits not enforced
4. Manual backups not being cleaned up (max_manual_backups not enforced)
5. Server disk too small for backup workload

## Safe Actions

- `cleanup_expired_backups` — run `cleanup_backup_retention()` immediately
- `reduce_backup_retention` — lower `BACKUP_MAX_MANUAL_BACKUPS_PER_TENANT`
- `delete_old_manual_backups` — list and delete oldest manual backups
- `verify_backup_local_dir_permissions` — ensure no permissions block deletion

## Forbidden Actions

- `delete_last_successful_backup` — never delete the only successful backup for a tenant
- `disable_backups_silently` — do not disable backups without notifying admin
- `chmod_777_backup_dir` — do not loosen permissions to work around space issue

## Diagnosis Steps

1. `df -h /opt/hostingguard-backups` — check disk usage
2. `du -sh /opt/hostingguard-backups/tenants/*` — identify largest tenant backup dirs
3. `SELECT hosting_id, COUNT(*), SUM(total_size_bytes) FROM tenant_backups WHERE status='completed' GROUP BY hosting_id ORDER BY 3 DESC` — find biggest consumers

## Recovery

1. Run `cleanup_backup_retention()` via admin endpoint or directly
2. Delete old manual backups manually if retention cleanup is insufficient
3. If disk is fundamentally too small: migrate backups to larger volume
4. Consider reducing `BACKUP_MAX_PER_TENANT_GB` in env vars
