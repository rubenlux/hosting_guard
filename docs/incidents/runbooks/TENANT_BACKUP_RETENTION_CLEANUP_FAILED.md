# TENANT_BACKUP_RETENTION_CLEANUP_FAILED

**Severity**: medium  
**Status**: confirmed  
**auto_repair**: false

## Description

The periodic backup retention cleanup job failed. Old backups are not being
deleted as expected, causing disk space to grow unboundedly.

## Symptoms

- `backup.retention.cleanup_failed` audit event
- Log: `cleanup_backup_retention failed: <error>`
- Old automatic backups accumulating past latest-only policy
- Disk usage growing even though new backups succeed

## Root Causes

1. DB connection error during cleanup
2. File system permission error when deleting backup directories
3. A backup directory was moved or symlinked outside the expected path
4. Race condition: cleanup attempted while backup was in progress

## Safe Actions

- `cleanup_expired_backups` — re-run cleanup manually via admin endpoint
- `verify_backup_local_dir_permissions` — check that the app can delete from backup dir
- `delete_old_manual_backups` — manually remove oldest manual backups if automated cleanup fails

## Forbidden Actions

- `delete_last_successful_backup` — never remove the last completed backup for a tenant
- `chmod_777_backup_dir` — do not relax permissions without security review

## Diagnosis Steps

1. Check scheduler logs: `docker logs hg_scheduler --tail 100 | grep retention`
2. Verify directory permissions: `ls -la /opt/hostingguard-backups/`
3. Check DB for stuck backups: `SELECT * FROM tenant_backups WHERE status IN ('running','pending') AND started_at < NOW() - INTERVAL '2 hours'`

## Recovery

1. Fix permissions if needed: `chown -R app:app /opt/hostingguard-backups`
2. Mark stuck backups as failed in DB
3. Re-run cleanup: call `cleanup_backup_retention()` from admin shell
