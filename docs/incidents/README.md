# Incident Knowledge Base — HostingGuard

This directory contains the operational incident knowledge base for HostingGuard. It covers known failure modes, their signatures, root causes, and remediation procedures.

---

## Directory Structure

```
docs/incidents/
├── README.md                    ← this file
├── INCIDENT_INDEX.md            ← table of all 24 known incidents
├── runbooks/                    ← one file per incident
│   ├── TRAEFIK_DOCKER_PROVIDER_UNHEALTHY.md
│   ├── TRAEFIK_CLIENT_VERSION_TOO_OLD.md
│   ├── FORWARDAUTH_MIDDLEWARE_DOCKER_MISSING.md
│   ├── FILE_PROVIDER_FORWARDAUTH_MIGRATION.md
│   ├── TENANT_PUBLIC_404_ROUTER_MISSING.md
│   ├── WELCOME_TO_NGINX_EMPTY_SITE.md
│   ├── CONTAINER_WITH_EMPTY_MOUNTS.md
│   ├── ZIP_IMPORT_PERMISSION_DENIED.md
│   ├── DASHBOARD_FALSE_100_HEALTH.md
│   ├── ROUTER_HEALTH_INCIDENTS_DELETED_BY_SYNC.md
│   ├── REPAIR_ENDPOINT_500_WITH_CORS.md
│   ├── TRAEFIK_DYNAMIC_DIR_RW_DENIED.md
│   ├── CUSTOM_DOMAINS_ACTIVITY_REPOSITORY_IMPORT_CRASH.md
│   ├── ADMIN_STAFF_CREATED_AT_TS_500.md
│   ├── ADMIN_TERMINATE_PIXEL_EVENTS_TYPE_MISMATCH.md
│   ├── RESOURCES_MISSING_CONTAINER_BREAKS_COLLECTOR.md
│   ├── WP_XMLRPC_EXPOSED_APACHE_RUNTIME.md
│   ├── GITHUB_CRA_OUTPUT_DIRECTORY_MISCONFIG.md
│   ├── RESOURCE_DISK_DF_OVERREPORT.md
│   ├── RESOURCE_WINDOW_TOO_TIGHT_EMPTY_DASHBOARD.md
│   ├── CLIENT_DIR_RESIDUAL_AFTER_TERMINATE.md
│   ├── COMPOUND_TLD_APEX_MISCLASSIFICATION.md
│   ├── FRONTEND_CHUNK_404_BLANK_SCREEN.md
│   └── SECURITY_UPLOAD_REJECTION_NOT_LOGGED.md
└── signatures/
    └── error_signatures.yml     ← machine-readable signature → incident mapping
```

---

## How to Use Runbooks

### During an active incident

1. Find the relevant error message or symptom.
2. Search `signatures/error_signatures.yml` for a matching pattern.
3. Open the corresponding runbook in `runbooks/`.
4. Read **Diagnóstico rápido** first — copy-paste the diagnostic commands.
5. Follow **Solución manual** only after confirming the root cause matches.
6. Check **Auto-remediation prohibido** before running any automated fix.

### Runbook sections

Each runbook follows this structure:

| Section | Purpose |
|---|---|
| **Síntoma** | What the operator or user observes |
| **Impacto** | Who is affected and how severely |
| **Evidencia** | Exact log lines or API responses to look for |
| **Causa raíz** | Technical explanation of why this fails |
| **Diagnósticos equivocados** | Common wrong assumptions to avoid |
| **Diagnóstico rápido** | Copy-paste commands to confirm the diagnosis |
| **Solución manual** | Step-by-step fix that a human executes |
| **Fix permanente** | Code or config changes to prevent recurrence |
| **Señales para detección automática** | Log patterns and metrics for automated alerting |
| **Auto-remediation permitido** | Actions the system can take without human approval |
| **Auto-remediation prohibido** | Actions that must never be automated |
| **Dashboard esperado** | What healthy metrics look like after resolution |
| **RAG usage** | Search terms for the RAG retrieval system |
| **Tests/Chaos** | Test cases and chaos scenarios to validate the fix |

---

## Runbook Front-Matter Schema

Each runbook has a YAML front-matter block:

```yaml
---
incident_id: <UPPERCASE_SNAKE_CASE>
incident_type: <category>
severity: critical|high|medium|low
status: confirmed
validated: true
auto_repair_allowed: true|false
safe_actions:
  - <action_id>   # must exist in the AI decision executor
forbidden_actions:
  - <action_id>
signatures:
  - "exact error string"
---
```

### incident_type values

| Type | Meaning |
|---|---|
| `application_crash` | Python/FastAPI exception crashes a route or service |
| `database_query_error` | PostgreSQL returns an error (wrong column, type mismatch, etc.) |
| `collector_crash` | Background metric or data collection job fails |
| `security_vulnerability` | Exposed endpoint or unblocked attack vector |
| `deploy_misconfiguration` | Wrong config during a GitHub or ZIP deploy |
| `metrics_false_positive` | Metric or alert value is incorrect (not a real problem) |
| `ui_data_gap` | Dashboard shows no data due to query parameters, not missing data |
| `data_residual` | Data or files left behind after a lifecycle operation |
| `domain_processing_error` | Custom domain parsing, SSL, or DNS error |
| `frontend_deploy_issue` | Frontend asset or cache problem after a deploy |
| `security_audit_gap` | Security event not recorded despite the check running |
| `traefik_routing_error` | Traefik config, middleware, or provider issue |

---

## How the RAG Matcher Works

The diagnostic engine uses RAG (Retrieval-Augmented Generation) to match incoming log lines, error messages, or operator descriptions to known incidents.

### Retrieval pipeline

1. **Input**: raw error text, log snippet, or symptom description.
2. **Embedding**: the input is embedded and compared against all indexed runbook chunks.
3. **Signature lookup**: `error_signatures.yml` provides exact-match patterns (confidence 1.0) for known error strings.
4. **Ranked results**: the top-K matching runbooks are returned with confidence scores.
5. **Human review**: the matched runbook is presented as a suggestion, not executed automatically.

### Tenant isolation

The RAG system is tenant-isolated:
- Runbooks are global (not per-tenant).
- Log context passed to the RAG query is scoped to the affected hosting/tenant.
- The RAG results never include data from other tenants' incidents.
- Test coverage: `tests/test_rag_tenant_isolation.py`.

### RAG usage section

Each runbook has a `## RAG usage` section with recommended search terms. When adding a new runbook, include:
- The exact error string that will appear in logs.
- Common paraphrases of the symptom.
- Related component names.

---

## When Auto-repair Is Allowed

Auto-repair is only allowed when ALL of the following are true:

1. `auto_repair_allowed: true` in the runbook front-matter.
2. The action is listed in `safe_actions` for that incident.
3. The action ID is registered in the AI decision executor's action registry.
4. The action is **idempotent** (safe to run multiple times).
5. The action does **not** modify production data or delete anything.
6. A human approval flag is NOT required (`requires_human_approval: false`).

### Current auto-repair-eligible incidents

| Incident | Safe action | What it does |
|---|---|---|
| RESOURCES_MISSING_CONTAINER_BREAKS_COLLECTOR | skip_missing_container_in_metrics | Adds missing container to skip list; collection continues for all other hostings |
| WP_XMLRPC_EXPOSED_APACHE_RUNTIME | block_xmlrpc_apache | Adds nginx `location = /xmlrpc.php { deny all; return 403; }` and reloads nginx inside the container |

All other incidents require human review and approval before any action is taken. The AI layer is **advisory only** — it suggests the matching runbook and safe actions, but cannot execute without human confirmation.

---

## Adding a New Runbook

1. Create a file in `runbooks/` named `<INCIDENT_ID>.md` using the standard template.
2. Fill all 12 sections. Do not leave sections empty — use "N/A" if genuinely not applicable.
3. Add the incident to `INCIDENT_INDEX.md`.
4. Add all error signatures to `signatures/error_signatures.yml` with unique `sig_NNN` IDs.
5. If auto-repair is allowed, register the `safe_actions` in the AI decision executor.
6. Add at least one test in the `Tests/Chaos` section and implement it in `tests/`.
7. Run `ruff check .` and `mypy .` if the runbook documents a code fix.

### Runbook ID convention

- `UPPERCASE_SNAKE_CASE`
- Descriptive: `COMPONENT_SYMPTOM` or `COMPONENT_CAUSE`
- Examples: `TRAEFIK_DOCKER_PROVIDER_UNHEALTHY`, `ADMIN_STAFF_CREATED_AT_TS_500`

### Severity guidelines

| Severity | Criteria |
|---|---|
| **critical** | Service completely down for all clients, or security breach in progress |
| **high** | Service broken for a subset of clients, or significant security risk |
| **medium** | Feature broken for affected clients, no data loss, workaround exists |
| **low** | Cosmetic, metrics, or non-urgent operational debt |

---

## Related Documentation

- `/docs/ARCHITECTURE.md` — system architecture and component descriptions
- `/docs/AI_CONTEXT.md` — AI advisory layer design and constraints
- `/docs/CURRENT_TASK.md` — open work items
- `tests/test_rag_tenant_isolation.py` — RAG isolation tests
- `tests/test_decision_pipeline.py` — decision pipeline tests including auto-repair gate
