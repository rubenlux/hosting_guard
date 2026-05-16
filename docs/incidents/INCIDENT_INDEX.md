# Incident Index — HostingGuard

**Total incidents**: 32  
**Last updated**: 2026-05-16  
**Runbooks location**: `docs/incidents/runbooks/`  
**Signatures map**: `docs/incidents/signatures/error_signatures.yml`

---

## Index Table

| # | ID | Severity | Status | auto_repair | Description |
|---|---|---|---|---|---|
| 1 | TRAEFIK_DOCKER_PROVIDER_UNHEALTHY | critical | confirmed | false | Traefik Docker provider reports unhealthy; containers are not automatically registered as backends. All new hostings fail to route. |
| 2 | TRAEFIK_CLIENT_VERSION_TOO_OLD | high | confirmed | false | Traefik binary or Docker client version mismatch: "client version 1.24 is too old". Routing updates may fail silently. |
| 3 | FORWARDAUTH_MIDDLEWARE_DOCKER_MISSING | critical | confirmed | false | Traefik middleware `hg-forwardauth@docker` does not exist; all requests bypass authentication. Auth enforcement is broken. |
| 4 | FILE_PROVIDER_FORWARDAUTH_MIGRATION | high | confirmed | false | Auth middleware migrated from Docker label to Traefik file provider YAML but some dynamic configs still reference the old Docker label name. Some routes bypass auth. |
| 5 | TENANT_PUBLIC_404_ROUTER_MISSING | high | confirmed | false | A tenant's public subdomain returns 404 because the Traefik router entry is missing from the file provider YAML in `/opt/traefik-dynamic/`. |
| 6 | WELCOME_TO_NGINX_EMPTY_SITE | medium | confirmed | false | The hosted site shows the default nginx welcome page instead of the WordPress or static site. The webroot is empty or nginx config points to wrong path. |
| 7 | CONTAINER_WITH_EMPTY_MOUNTS | critical | confirmed | false | A hosting container starts but all bind mounts are empty. `/var/www/html/` and/or `/var/lib/mysql/` are missing data. Site is broken and database is unreachable. |
| 8 | ZIP_IMPORT_PERMISSION_DENIED | medium | confirmed | false | The ARQ worker import pipeline fails with `PermissionError` or `Permission denied` when extracting a zip file. The hosting remains in `importing` state indefinitely. |
| 9 | DASHBOARD_FALSE_100_HEALTH | medium | confirmed | false | The health dashboard shows 100% healthy for all hostings but some containers are actually stopped or unresponsive. Health probe logic has a false-positive bug. |
| 10 | ROUTER_HEALTH_INCIDENTS_DELETED_BY_SYNC | high | confirmed | false | The Traefik file provider sync job deletes and rewrites all YAML files in `/opt/traefik-dynamic/`, inadvertently removing manually added routes or router health annotations. |
| 11 | REPAIR_ENDPOINT_500_WITH_CORS | medium | confirmed | false | The `/decision/repair` endpoint returns 500 and the error is masked by a CORS failure in the browser. The actual error is a backend exception hidden by the CORS pre-flight failure. |
| 12 | TRAEFIK_DYNAMIC_DIR_RW_DENIED | critical | confirmed | false | Traefik or the app cannot write to `/opt/traefik-dynamic/`. New hostings cannot be provisioned and domain changes cannot take effect. |
| 13 | CUSTOM_DOMAINS_ACTIVITY_REPOSITORY_IMPORT_CRASH | medium | confirmed | false | `activity_service.py` crashes with `ImportError` or `AttributeError` on `custom_domain` when loading activity for a hosting with a custom domain set. Admin activity feed is broken for those hostings. |
| 14 | ADMIN_STAFF_CREATED_AT_TS_500 | medium | confirmed | false | `GET /admin/staff` returns 500 with `ProgrammingError: column "created_at_ts" does not exist`. Column name in model/query is `created_at_ts` but actual PostgreSQL column is `created_at`. |
| 15 | ADMIN_TERMINATE_PIXEL_EVENTS_TYPE_MISMATCH | medium | confirmed | false | Admin terminate or pixel events endpoint returns 500 with `operator does not exist: text = integer`. `hosting_id` column in `pixel_events` is `TEXT` but query passes an integer parameter. |
| 16 | RESOURCES_MISSING_CONTAINER_BREAKS_COLLECTOR | medium | confirmed | true | Resource collector crashes on `No such container: user_X_Y` and aborts the ENTIRE poll cycle, leaving all hostings without metrics. Fix: skip missing containers and continue. |
| 17 | WP_XMLRPC_EXPOSED_APACHE_RUNTIME | high | confirmed | true | `/xmlrpc.php` is publicly accessible (HTTP 200) on WordPress hostings. Being abused for brute force or DDoS amplification. Fix: block at nginx level inside container. |
| 18 | GITHUB_CRA_OUTPUT_DIRECTORY_MISCONFIG | medium | confirmed | false | CRA site deployed from GitHub shows blank page or 404. Output directory is configured as `public/` but CRA builds to `build/`. Requires user action to fix. |
| 19 | RESOURCE_DISK_DF_OVERREPORT | low | confirmed | false | Dashboard shows disk at 90-100% but actual client file usage is 20-30%. `df` inside container over-reports due to Docker overlay2 filesystem layers. Fix: use `SizeRw` from `docker inspect`. |
| 20 | RESOURCE_WINDOW_TOO_TIGHT_EMPTY_DASHBOARD | low | confirmed | false | Resource dashboard shows empty charts. Root cause: time window query is narrower than the 5-minute collection interval, returning 0 data points. Fix: use wider default window (1h). |
| 21 | CLIENT_DIR_RESIDUAL_AFTER_TERMINATE | low | confirmed | false | `/opt/clients/{container_name}/` directory remains on host after hosting termination. Wastes disk, may violate data retention policy, risks data exposure on container name reuse. |
| 22 | COMPOUND_TLD_APEX_MISCLASSIFICATION | medium | confirmed | false | Custom domains with compound TLDs (`.com.ar`, `.co.uk`) have incorrect apex extraction. SSL cert requests and DNS verification target the wrong domain. Fix: use `tldextract`. |
| 23 | FRONTEND_CHUNK_404_BLANK_SCREEN | high | confirmed | false | After frontend deploy, users with open tabs see blank screen: "Failed to fetch dynamically imported module". Old chunk hashes referenced in cached HTML no longer exist. Fix: set `no-cache` on `index.html`. |
| 24 | SECURITY_UPLOAD_REJECTION_NOT_LOGGED | medium | confirmed | false | Security module rejects dangerous uploads (PHP shells, double-extension files) but does NOT emit security events. Attacks are blocked but invisible in Security Center and cannot trigger IP-based detection. |
| 25 | TENANT_CLOUDFLARE_526_ORIGIN_TLS_INVALID | high | confirmed | false | Cloudflare returns 526 "Invalid SSL certificate" for a tenant subdomain. Origin TLS certificate is expired, missing, or not served correctly. Public route is unreachable. |
| 26 | TENANT_NGINX_403_EMPTY_OR_MISSING_INDEX | high | confirmed | false | Tenant static nginx container returns HTTP 403 because the webroot (/usr/share/nginx/html) is empty — no index.html exists. Autoindex is off so nginx denies directory listing. |
| 27 | TENANT_ROUTE_DOCKER_LABELS_ONLY | high | confirmed | false | Tenant route is served via Traefik Docker labels only — the File Provider YAML (`/opt/traefik-dynamic/tenant-{id}.yml`) is missing. If the Docker provider fails or a version mismatch occurs, the tenant becomes unreachable. Safe actions: `regenerate_tenant_file_provider_route`, `migrate_tenant_route_docker_labels_to_file`, `validate_traefik_dynamic_yaml`, `verify_forwardauth_file_middleware`. Forbidden: `rely_on_docker_provider_only`, `bypass_forwardauth`, `mark_healthy_without_file_provider_route`, `disable_router_health_check`. |
| 28 | TENANT_BACKUP_FILES_PATH_MISSING | medium | confirmed | false | Backup job cannot find `/opt/clients/<container_name>`. Host directory missing, deleted, or container was renamed. Safe actions: `verify_backup_local_dir_permissions`, `run_files_backup_only`. Forbidden: `overwrite_live_files_without_snapshot`. |
| 29 | TENANT_BACKUP_DATABASE_DUMP_FAILED | medium | confirmed | false | MariaDB/MySQL dump via `docker exec mariadb-dump` failed. Container stopped, dump tool missing, or credentials wrong. Safe actions: `inspect_db_container_env`, `run_files_backup_only`. Forbidden: `log_database_password`, `disable_backups_silently`. |
| 30 | TENANT_BACKUP_LOCAL_STORAGE_FULL | high | confirmed | false | Local backup storage `/opt/hostingguard-backups` has insufficient disk space. Old backups not being cleaned up. Safe actions: `cleanup_expired_backups`, `reduce_backup_retention`, `delete_old_manual_backups`. Forbidden: `delete_last_successful_backup`, `chmod_777_backup_dir`. |
| 31 | TENANT_BACKUP_RETENTION_CLEANUP_FAILED | medium | confirmed | false | Periodic backup retention cleanup job failed. Old backups accumulating, disk growing. Safe actions: `cleanup_expired_backups`, `verify_backup_local_dir_permissions`. Forbidden: `delete_last_successful_backup`. |
| 32 | TENANT_BACKUP_NOT_CONFIGURED | low | confirmed | false | `BACKUP_ENABLED=false` — backup feature is disabled. No tenant_backups records being created. Safe actions: set `BACKUP_ENABLED=true` in env. |

---

## Severity Distribution

| Severity | Count | IDs |
|---|---|---|
| critical | 4 | TRAEFIK_DOCKER_PROVIDER_UNHEALTHY, FORWARDAUTH_MIDDLEWARE_DOCKER_MISSING, CONTAINER_WITH_EMPTY_MOUNTS, TRAEFIK_DYNAMIC_DIR_RW_DENIED |
| high | 10 | TRAEFIK_CLIENT_VERSION_TOO_OLD, FILE_PROVIDER_FORWARDAUTH_MIGRATION, TENANT_PUBLIC_404_ROUTER_MISSING, ROUTER_HEALTH_INCIDENTS_DELETED_BY_SYNC, WP_XMLRPC_EXPOSED_APACHE_RUNTIME, FRONTEND_CHUNK_404_BLANK_SCREEN, TENANT_CLOUDFLARE_526_ORIGIN_TLS_INVALID, TENANT_NGINX_403_EMPTY_OR_MISSING_INDEX, TENANT_ROUTE_DOCKER_LABELS_ONLY, TENANT_BACKUP_LOCAL_STORAGE_FULL |
| medium | 13 | WELCOME_TO_NGINX_EMPTY_SITE, ZIP_IMPORT_PERMISSION_DENIED, DASHBOARD_FALSE_100_HEALTH, REPAIR_ENDPOINT_500_WITH_CORS, CUSTOM_DOMAINS_ACTIVITY_REPOSITORY_IMPORT_CRASH, ADMIN_STAFF_CREATED_AT_TS_500, ADMIN_TERMINATE_PIXEL_EVENTS_TYPE_MISMATCH, RESOURCES_MISSING_CONTAINER_BREAKS_COLLECTOR, GITHUB_CRA_OUTPUT_DIRECTORY_MISCONFIG, COMPOUND_TLD_APEX_MISCLASSIFICATION, SECURITY_UPLOAD_REJECTION_NOT_LOGGED, TENANT_BACKUP_FILES_PATH_MISSING, TENANT_BACKUP_DATABASE_DUMP_FAILED, TENANT_BACKUP_RETENTION_CLEANUP_FAILED |
| low | 4 | RESOURCE_DISK_DF_OVERREPORT, RESOURCE_WINDOW_TOO_TIGHT_EMPTY_DASHBOARD, CLIENT_DIR_RESIDUAL_AFTER_TERMINATE, TENANT_BACKUP_NOT_CONFIGURED |

---

## Auto-repair Eligible

| ID | Safe action |
|---|---|
| RESOURCES_MISSING_CONTAINER_BREAKS_COLLECTOR | skip_missing_container_in_metrics |
| WP_XMLRPC_EXPOSED_APACHE_RUNTIME | block_xmlrpc_apache |

All other incidents require human intervention before any remediation action is taken.

---

## Runbook Coverage

Runbooks exist for incidents 13–32. Runbooks for incidents 1–12 are located in the same `runbooks/` directory.

To add a new incident, see `docs/incidents/README.md`.
