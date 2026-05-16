# TENANT_BACKUP_NOT_CONFIGURED

**Severity**: low  
**Status**: confirmed  
**auto_repair**: false

## Description

A backup was requested but `BACKUP_ENABLED=false` in the environment configuration.
No backups are being created. This is not an error per se but means the backup
feature is intentionally disabled.

## Symptoms

- Backup API returns `error_code=backup_not_configured`
- `backup_tenants_job` logs: `BACKUP_ENABLED=false, skipping`
- No `tenant_backups` records being created

## Root Causes

1. `BACKUP_ENABLED=false` in `.env` or docker-compose
2. Backup feature not yet activated for this environment
3. Backup temporarily disabled during maintenance

## Safe Actions

- Set `BACKUP_ENABLED=true` in environment config to activate backups
- Verify `BACKUP_LOCAL_DIR=/opt/hostingguard-backups` directory exists and is writable

## Forbidden Actions

- `disable_backups_silently` — if disabling, communicate to affected users

## Configuration Checklist

```env
BACKUP_ENABLED=true
BACKUP_STORAGE_DRIVER=local
BACKUP_LOCAL_DIR=/opt/hostingguard-backups
BACKUP_DATABASE_ENABLED=true
BACKUP_FILES_ENABLED=true
BACKUP_MAX_MANUAL_BACKUPS_PER_TENANT=2
BACKUP_PRE_RESTORE_TTL_HOURS=24
```

## Recovery

1. Set `BACKUP_ENABLED=true` in `/opt/deploy/.env`
2. Restart app and scheduler containers: `docker compose restart app hg_scheduler`
3. Test with: `POST /hosting/hostings/{id}/backups` (admin user)
