---
incident_id: P4B_TENANT_CAN_REACH_PLATFORM_INTERNAL_SERVICES
incident_type: tenant_network_isolation
severity: critical
status: confirmed
validated: true
auto_repair_allowed: false
safe_actions:
  - validate_tenant_network_isolation
  - migrate_tenant_to_isolated_network
forbidden_actions:
  - add_tenant_to_platform_network
  - run_tenant_container_as_privileged
  - mount_docker_sock_in_tenant_container
signatures:
  - "tenant can reach redis"
  - "tenant can reach hosting_guard"
  - "redis:6379 open"
  - "tcp open: redis:6379"
  - "tenant can reach platform services"
  - "deploy_hosting_network"
  - "platform service isolation"
---

# P4B — TENANT_CAN_REACH_PLATFORM_INTERNAL_SERVICES

Tenant container can resolve DNS and connect TCP/HTTP to platform-internal services
(redis, hosting_guard, prometheus, alertmanager) due to a flat Docker network.

**Full runbook**: `docs/knowledge/incidents/P4B_TENANT_CAN_REACH_PLATFORM_INTERNAL_SERVICES.md`

## Síntoma

A tenant container (`user_*`) can reach platform-internal services that must be invisible
from `deploy_tenant_edge_network`. Confirmed when any of these return OPEN/resolved:

- `redis:6379` (TCP open)
- `hosting_guard:8000` (DNS resolved, HTTP reachable)
- `prometheus:9090` (DNS resolved, HTTP reachable)
- `alertmanager:9093` (DNS resolved, HTTP reachable)

## Causa raíz

Tenant container is on `deploy_hosting_network` (flat network) instead of being
exclusively on `deploy_tenant_edge_network`. All services on the flat network share
DNS resolution and TCP visibility.

## Fix

```bash
# Dry-run first
sudo ./scripts/ops/migrate_tenants_to_tenant_edge_network.sh

# Apply
sudo APPLY=true ./scripts/ops/migrate_tenants_to_tenant_edge_network.sh
```

## Validación

```bash
sudo ./scripts/security/validate_tenant_network_isolation.sh <CONTAINER_NAME>
# Expected: 25 passed, 0 failed — SECURE
```

## Diagnóstico rápido

```bash
docker inspect \
  --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' \
  <CONTAINER_NAME>
# Expected: deploy_tenant_edge_network (only)
```
