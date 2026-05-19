---
incident_id: P4C_TENANT_RUNTIME_HARDENING
incident_type: tenant_runtime_hardening
severity: high
status: confirmed
validated: true
auto_repair_allowed: false
safe_actions:
  - validate_tenant_runtime_hardening
  - harden_existing_tenant_containers
forbidden_actions:
  - run_tenant_container_as_privileged
  - mount_docker_sock_in_tenant_container
  - add_tenant_to_platform_network
signatures:
  - "tenant container has no pids limit"
  - "no no-new-privileges"
  - "No pids limit"
  - "fork-bomb possible"
  - "pids limit: None"
  - "no-new-privileges not set"
---

# P4C — TENANT_RUNTIME_HARDENING

Tenant container is missing one or more runtime security controls:
`no-new-privileges`, `pids-limit`, memory/CPU limits, or read-only site mount.

**Full runbook**: `docs/knowledge/security/P4C_TENANT_RUNTIME_HARDENING.md`

## Síntoma

`validate_runtime_hardening.sh` reports WARN or FAIL for a tenant container:

- `[WARN] no-new-privileges not set` — tenant process can escalate via setuid
- `[WARN] No pids limit — fork-bomb possible` — no fork() throttle on the host
- `[WARN] No memory limit` — tenant can exhaust host RAM
- `[WARN] No cpu quota` — tenant can monopolize CPU
- `[FAIL] Container is PRIVILEGED` — full host access (critical)
- `[FAIL] docker.sock mounted` — full Docker daemon access (critical)

## Causa raíz

Container was created before the hardening policy (`tenant_hardening_flags()` in
`app/infra/docker_client.py`) was introduced, or was created via a path that doesn't
include the hardening flags.

## Fix

```bash
# Validate current state
sudo ./scripts/security/validate_runtime_hardening.sh

# Harden existing containers (dry-run by default)
sudo ./scripts/ops/harden_existing_tenants.sh

# Apply
sudo APPLY=true ./scripts/ops/harden_existing_tenants.sh
```

## Validación

```bash
sudo ./scripts/security/validate_runtime_hardening.sh
# Expected: Results: N passed, 0 warnings, 0 failures — SECURE

sudo ./scripts/security/validate_runtime_hardening.sh --tenant <CONTAINER_NAME>
```

## Diagnóstico rápido

```bash
docker inspect \
  --format '{{.HostConfig.SecurityOpt}} | pids={{.HostConfig.PidsLimit}} | mem={{.HostConfig.Memory}}' \
  <CONTAINER_NAME>
# Expected: [no-new-privileges:true] | pids=200 | mem=<N>
```
