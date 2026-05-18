# Knowledge Base — HostingGuard

Documentos de conocimiento operativo para el RAG de HostingGuard. Cada documento mapea
un síntoma a una causa raíz, fix aplicado y comandos de validación.

**Última actualización**: 2026-05-18

---

## Incidents

| Severidad | ID | Área | Resumen |
|---|---|---|---|
| `critical` | [P4B_TENANT_CAN_REACH_PLATFORM_INTERNAL_SERVICES](incidents/P4B_TENANT_CAN_REACH_PLATFORM_INTERNAL_SERVICES.md) | docker-networking | Los contenedores tenant podían resolver DNS y conectar TCP/HTTP a servicios internos (redis, hosting_guard, prometheus, alertmanager) por estar en una red Docker plana compartida |
| `medium` | [VALIDATE_TENANT_NETWORK_HTTP_000_FALSE_FAIL](incidents/VALIDATE_TENANT_NETWORK_HTTP_000_FALSE_FAIL.md) | validation-script | `validate_tenant_network_isolation.sh` emitía falsos FAIL con código `000000` para servicios bloqueados; causa: `|| echo 000` duplicaba el output de curl |

---

## Runbooks

| ID | Área | Resumen |
|---|---|---|
| [TENANT_NETWORK_ISOLATION](runbooks/TENANT_NETWORK_ISOLATION.md) | docker-networking | Diagnosticar, remediar y revalidar el aislamiento de red de tenants; arquitectura de 4 redes, comandos de migración, auditoría de todos los tenants |

---

## Security Hardening

| Severidad | ID | Área | Resumen |
|---|---|---|---|
| `high` | [P4C_TENANT_RUNTIME_HARDENING](security/P4C_TENANT_RUNTIME_HARDENING.md) | tenant-runtime | Aplicación de `no-new-privileges`, `pids-limit 200`, límites de memoria/CPU y mounts `:ro` a todos los tenants existentes; resultado final: 54 passed, 0 warnings, 0 failures |

---

## Lookup rápido por síntoma

| Síntoma | Documento |
|---|---|
| Tenant puede conectar a redis / prometheus / alertmanager | [P4B_TENANT_CAN_REACH_PLATFORM_INTERNAL_SERVICES](incidents/P4B_TENANT_CAN_REACH_PLATFORM_INTERNAL_SERVICES.md) |
| `validate_tenant_network_isolation.sh` devuelve `000000` | [VALIDATE_TENANT_NETWORK_HTTP_000_FALSE_FAIL](incidents/VALIDATE_TENANT_NETWORK_HTTP_000_FALSE_FAIL.md) |
| Script de validación marca FAIL HTTP pero PASS en DNS y TCP | [VALIDATE_TENANT_NETWORK_HTTP_000_FALSE_FAIL](incidents/VALIDATE_TENANT_NETWORK_HTTP_000_FALSE_FAIL.md) |
| Cómo aislar un tenant a `deploy_tenant_edge_network` | [TENANT_NETWORK_ISOLATION](runbooks/TENANT_NETWORK_ISOLATION.md) |
| Cómo migrar tenants de red plana a red aislada | [TENANT_NETWORK_ISOLATION](runbooks/TENANT_NETWORK_ISOLATION.md) |
| `validate_runtime_hardening.sh` muestra WARN por pids/memory/no-new-privileges | [P4C_TENANT_RUNTIME_HARDENING](security/P4C_TENANT_RUNTIME_HARDENING.md) |
| Tenant sin `--security-opt no-new-privileges:true` o `--pids-limit` | [P4C_TENANT_RUNTIME_HARDENING](security/P4C_TENANT_RUNTIME_HARDENING.md) |
| Cómo hardenizar contenedores tenant existentes sin recrear manualmente | [P4C_TENANT_RUNTIME_HARDENING](security/P4C_TENANT_RUNTIME_HARDENING.md) |

---

## Scripts de validación y operaciones

| Script | Propósito |
|---|---|
| `scripts/security/validate_tenant_network_isolation.sh` | Verifica aislamiento DNS/TCP/HTTP de un tenant contra todos los servicios internos |
| `scripts/security/validate_runtime_hardening.sh` | Verifica flags de runtime de todos los tenants (`user_*`) |
| `scripts/security/redact_compose_config.sh` | Ejecuta `docker compose config` con secretos redactados para reportes |
| `scripts/ops/migrate_tenants_to_tenant_edge_network.sh` | Migra tenants de red plana a `deploy_tenant_edge_network` (dry-run por defecto) |
| `scripts/ops/harden_existing_tenants.sh` | Recrea tenants con hardening flags; preserva config original, rollback automático |

---

## Documentos relacionados (base existente)

- [Incident Index](../incidents/INCIDENT_INDEX.md) — 32 incidentes operativos con runbooks
- [Architecture](../ARCHITECTURE.md) — Arquitectura completa del sistema
- [Current Task](../CURRENT_TASK.md) — Issues abiertos
