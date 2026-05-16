# TENANT_BACKUP_FILES_PATH_MISSING

**Severity**: medium  
**Status**: confirmed  
**auto_repair**: false

## Description

The backup job cannot find the host directory for a tenant's static files.
Expected path: `/opt/clients/<container_name>` — directory is missing, deleted, or
the container was renamed without the host directory being recreated.

## Symptoms

- `backup.tenant.failed` audit event with `error_code=backup_files_path_missing`
- Backup record status=failed in `tenant_backups`
- Log: `backup_files_path_missing:/opt/clients/<container_name>`

## Root Causes

1. Container was terminated but `/opt/clients/<container_name>/` was deleted
2. Container was renamed without migrating the host directory
3. Provisioning never created the host mount directory
4. Manual rm of `/opt/clients/<container_name>` by mistake

## Safe Actions

- `verify_backup_local_dir_permissions` — check that `/opt/clients/` exists and is readable
- `run_files_backup_only` after recreating the directory
- Check `container_name` in `hostings` table matches actual directory name

## Forbidden Actions

- `overwrite_live_files_without_snapshot` — never replace client files without backup
- `chmod_777_backup_dir` — do not world-write the backup directory

## Diagnosis Steps

1. `ls /opt/clients/<container_name>` — confirm directory exists
2. `docker inspect <container_name> | jq '.[0].Mounts'` — verify bind mount
3. `SELECT container_name FROM hostings WHERE hosting_id=<id>` — confirm name
4. If directory missing and container running: site is serving from memory only

## Recovery

1. Recreate directory if lost: `mkdir -p /opt/clients/<container_name>`
2. If container has content: copy via `docker cp <container>:/usr/share/nginx/html/. /opt/clients/<container_name>/`
3. Re-run backup
