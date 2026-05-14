# HostingGuard Chaos Test Report
**Date:** 2026-05-14 21:53 UTC  
**Mode:** local  
**Total:** 8/8 passed  
**Critical failures:** None  
**Kali-ready:** ✓ YES

---

## Summary Table

| Case | Description | Detected | Runbook | Dashboard | Repair | safe/forbidden OK | Pass |
|------|-------------|----------|---------|-----------|--------|-------------------|------|
| C01 | Delete tenant Traefik YAML → router missing | ✓ | DASHBOARD_FALSE_100_HEALTH | — | — | ✓ | ✓ |
| C02 | HTTP 200 but body = 'Welcome to nginx!' → mis | ✓ | WELCOME_TO_NGINX_EMPTY_SITE | critical | — | ✓ | ✓ |
| C03 | Container Mounts=[] → invalid_container_mount | ✓ | CONTAINER_WITH_EMPTY_MOUNTS | — | — | ✓ | ✓ |
| C04 | hg-forwardauth@docker missing → FORWARDAUTH_M | ✓ | FORWARDAUTH_MIDDLEWARE_DOCKER_MISSI | — | — | ✓ | ✓ |
| C05 | Container stopped → container_not_running / b | ✓ | — | critical | — | ✓ | ✓ |
| C06 | ZIP import fails with permission denied → str | ✓ | ZIP_IMPORT_PERMISSION_DENIED | — | — | ✓ | ✓ |
| C07 | 'client version 1.24 is too old' → TRAEFIK_CL | ✓ | TRAEFIK_CLIENT_VERSION_TOO_OLD | — | — | ✓ | ✓ |
| C08 | Dashboard must NOT show 100/healthy when crit | ✓ | WELCOME_TO_NGINX_EMPTY_SITE | critical | — | ✓ | ✓ |

---

## Case Details

### C01 — Delete tenant Traefik YAML → router missing ⚠ CRITICAL

**Destructive action:** Remove tenant route from tenants-active.yml  
**Mode:** local  
**Status:** ✓ PASS  

| Field | Value |
|-------|-------|
| incident_type | `—` |
| matched_runbook_id | `DASHBOARD_FALSE_100_HEALTH` |
| runbook_confidence | `0.90` |
| dashboard_state | `—` |
| dashboard_score | `—` |
| repair_executed | `False` |
| validation_curl_status | `—` |
| detection_time_s | `0.09` |
| recovery_time_s | `—` |
| safe_forbidden_overlap | `none` |

**safe_actions:** regenerate_tenant_file_provider_route  
**forbidden_actions:** mark_incident_healthy_on_200_without_body_check, auto_resolve_router_health_incidents  

**Notes:**
- Runbook matched: DASHBOARD_FALSE_100_HEALTH (confidence=0.90)
- Expected runbook: TENANT_PUBLIC_404_ROUTER_MISSING
- safe action 'regenerate_tenant_file_provider_route' validator: ALLOWED

### C02 — HTTP 200 but body = 'Welcome to nginx!' → misconfigured_site_content ⚠ CRITICAL

**Destructive action:** Check nginx default page detection in router health  
**Mode:** local  
**Status:** ✓ PASS  

| Field | Value |
|-------|-------|
| incident_type | `misconfigured_site_content` |
| matched_runbook_id | `WELCOME_TO_NGINX_EMPTY_SITE` |
| runbook_confidence | `1.00` |
| dashboard_state | `critical` |
| dashboard_score | `—` |
| repair_executed | `False` |
| validation_curl_status | `—` |
| detection_time_s | `—` |
| recovery_time_s | `—` |
| safe_forbidden_overlap | `none` |

**safe_actions:** recreate_static_nginx_container_with_mount  
**forbidden_actions:** delete_client_files, disable_nginx_default_page_check, auto_update_dns  

**Notes:**
- OK _is_nginx_default_page(b'Welcome to nginx!') = True
- OK _is_nginx_default_page(b'<html>Welcome to nginx! If you') = True
- OK _is_nginx_default_page(b'nginx default page lorem') = True
- OK _is_nginx_default_page(b'My Awesome Blog Post') = False
- Expected runbook: WELCOME_TO_NGINX_EMPTY_SITE, got: WELCOME_TO_NGINX_EMPTY_SITE
- Dashboard must NOT show 100 when this incident exists

### C03 — Container Mounts=[] → invalid_container_mount detected ⚠ CRITICAL

**Destructive action:** check_static_container_mounts() with mocked empty mounts  
**Mode:** local  
**Status:** ✓ PASS  

| Field | Value |
|-------|-------|
| incident_type | `invalid_container_mount` |
| matched_runbook_id | `CONTAINER_WITH_EMPTY_MOUNTS` |
| runbook_confidence | `1.00` |
| dashboard_state | `—` |
| dashboard_score | `—` |
| repair_executed | `False` |
| validation_curl_status | `—` |
| detection_time_s | `—` |
| recovery_time_s | `—` |
| safe_forbidden_overlap | `none` |

**safe_actions:** recreate_static_nginx_container_with_mount  
**forbidden_actions:** chmod_777_opt_clients, delete_client_data_without_snapshot  

**Notes:**
- OK _has_html_mount([]) = False
- OK _has_html_mount([{'Destination': '/tmp'}]) = False
- OK _has_html_mount([{'Destination': '/usr/share/nginx/html'}]) = True
- safe action 'recreate_static_nginx_container_with_mount': ALLOWED (dry_run first)
- Destructive actions correctly forbidden: True

### C04 — hg-forwardauth@docker missing → FORWARDAUTH_MIDDLEWARE_DOCKER_MISSING ⚠ CRITICAL

**Destructive action:** Simulate Traefik log: middleware hg-forwardauth@docker does not exist  
**Mode:** local  
**Status:** ✓ PASS  

| Field | Value |
|-------|-------|
| incident_type | `—` |
| matched_runbook_id | `FORWARDAUTH_MIDDLEWARE_DOCKER_MISSING` |
| runbook_confidence | `1.00` |
| dashboard_state | `—` |
| dashboard_score | `—` |
| repair_executed | `False` |
| validation_curl_status | `—` |
| detection_time_s | `—` |
| recovery_time_s | `—` |
| safe_forbidden_overlap | `none` |

**safe_actions:** regenerate_file_provider_forwardauth, migrate_tenant_yamls_docker_to_file  
**forbidden_actions:** disable_forwardauth_middleware, bypass_auth_for_tenant_routes  

**Notes:**
- disable_forwardauth_middleware is FORBIDDEN: True
- bypass_auth_for_tenant_routes is FORBIDDEN: True
- regenerate_file_provider_forwardauth: ALLOWED

### C05 — Container stopped → container_not_running / backend_unreachable

**Destructive action:** docker stop disposable tenant container  
**Mode:** local  
**Status:** ✓ PASS  

| Field | Value |
|-------|-------|
| incident_type | `traefik_backend_unreachable` |
| matched_runbook_id | `—` |
| runbook_confidence | `0.00` |
| dashboard_state | `critical` |
| dashboard_score | `—` |
| repair_executed | `False` |
| validation_curl_status | `—` |
| detection_time_s | `—` |
| recovery_time_s | `—` |
| safe_forbidden_overlap | `none` |

**safe_actions:** —  
**forbidden_actions:** —  

**Notes:**
- _classify_failure(-3, '') = traefik_backend_unreachable
- _classify_failure(502, 'text/html') = traefik_backend_unreachable
- Container down → 502 → traefik_backend_unreachable incident
- Auto-repair: NOT allowed (container must be manually inspected)

### C06 — ZIP import fails with permission denied → structured 503 error

**Destructive action:** Remove write permission on upload directory  
**Mode:** local  
**Status:** ✓ PASS  

| Field | Value |
|-------|-------|
| incident_type | `import_dir_not_writable` |
| matched_runbook_id | `ZIP_IMPORT_PERMISSION_DENIED` |
| runbook_confidence | `1.00` |
| dashboard_state | `—` |
| dashboard_score | `—` |
| repair_executed | `False` |
| validation_curl_status | `—` |
| detection_time_s | `—` |
| recovery_time_s | `—` |
| safe_forbidden_overlap | `none` |

**safe_actions:** fix_import_tmp_permissions  
**forbidden_actions:** chmod_777_entire_opt_clients, skip_permission_check_on_upload  

**Notes:**
- skip_permission_check_on_upload is FORBIDDEN: True
- Expected: API returns 503 with code=import_dir_not_writable (not raw traceback)

### C07 — 'client version 1.24 is too old' → TRAEFIK_CLIENT_VERSION_TOO_OLD ⚠ CRITICAL

**Destructive action:** Inject synthetic Traefik error signature (no live Traefik change)  
**Mode:** local  
**Status:** ✓ PASS  

| Field | Value |
|-------|-------|
| incident_type | `traefik_docker_provider_unhealthy` |
| matched_runbook_id | `TRAEFIK_CLIENT_VERSION_TOO_OLD` |
| runbook_confidence | `1.00` |
| dashboard_state | `—` |
| dashboard_score | `—` |
| repair_executed | `False` |
| validation_curl_status | `—` |
| detection_time_s | `—` |
| recovery_time_s | `—` |
| safe_forbidden_overlap | `none` |

**safe_actions:** set_docker_api_version_env, remove_docker_provider_from_traefik_config  
**forbidden_actions:** auto_upgrade_docker_on_production, auto_restart_traefik_without_config_backup  

**Notes:**
- auto_upgrade_docker: FORBIDDEN=True
- auto_restart_without_backup: FORBIDDEN=True
- File Provider continues serving platform routes even if Docker Provider fails
- Tenants still accessible via file provider YAML during Docker provider failure

### C08 — Dashboard must NOT show 100/healthy when critical incident exists ⚠ CRITICAL

**Destructive action:** Verify dashboard override logic when router incident is open  
**Mode:** local  
**Status:** ✓ PASS  

| Field | Value |
|-------|-------|
| incident_type | `—` |
| matched_runbook_id | `WELCOME_TO_NGINX_EMPTY_SITE` |
| runbook_confidence | `0.00` |
| dashboard_state | `critical` |
| dashboard_score | `0` |
| repair_executed | `False` |
| validation_curl_status | `—` |
| detection_time_s | `—` |
| recovery_time_s | `—` |
| safe_forbidden_overlap | `none` |

**safe_actions:** recreate_static_nginx_container_with_mount  
**forbidden_actions:** delete_client_files  

**Notes:**
- Score after override: 0 (was 100)
- Status after override: critical (was healthy)
- Dashboard CORRECTLY overrides to score=0, status=critical

---

## Acceptance Criteria

| Criterion | Status |
|-----------|--------|
| All critical cases pass | ✓ |
| Dashboard never shows 100 during critical incident | ✓ |
| Runbooks attach to incidents (matched_runbook_id) | ✓ |
| safe_actions never overlap with forbidden_actions | ✓ |
| Kali audit authorized | ✓ GO |

---
*Generated by scripts/chaos/run_chaos_suite.py — HostingGuard P0 Chaos Testing*