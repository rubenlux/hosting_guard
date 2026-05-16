# TENANT_BACKUP_DATABASE_DUMP_FAILED

**Severity**: medium  
**Status**: confirmed  
**auto_repair**: false

## Description

The MariaDB/MySQL dump via `docker exec` failed during backup. The dump command
(`mariadb-dump` or `mysqldump`) returned a non-zero exit code or produced
an empty/truncated output.

## Symptoms

- `backup.tenant.failed` audit event with `error_code=backup_database_dump_failed`
- Backup record status=failed in `tenant_backups`
- Full backup (backup_type=full): database skipped, files still backed up
- Database-only backup: entire backup fails
- Log: `backup_database_dump_failed:<stderr excerpt>`

## Root Causes

1. DB container not running or crashed
2. `mariadb-dump` / `mysqldump` not installed in the DB container image
3. Wrong credentials: `MYSQL_USER`/`MYSQL_PASSWORD`/`MYSQL_DATABASE` env vars missing or wrong
4. MariaDB in recovery mode or too busy to accept new connections
5. Dump timeout exceeded (180s default)

## Safe Actions

- `inspect_db_container_env` — docker inspect env vars (never log passwords to console)
- `run_files_backup_only` — run files-only backup while DB issue is investigated

## Forbidden Actions

- `log_database_password` — never print or log MYSQL_PASSWORD
- `disable_backups_silently` — do not mark backup as healthy if DB dump failed

## Diagnosis Steps

1. `docker ps | grep <db_container>` — verify container is running
2. `docker inspect <db_container> | jq '.[0].State'` — check state
3. `docker exec <db_container> mariadb-dump --version` — verify dump tool exists
4. Check container logs: `docker logs <db_container> --tail 50`

## Recovery

1. If container stopped: restart with `docker start <db_container>`
2. If credentials wrong: check env vars in compose file, not in code
3. Run backup again after fix
