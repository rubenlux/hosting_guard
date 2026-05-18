---
type: runbook
severity: critical
system: hostingguard
area: docker-networking
status: resolved
rag_priority: high
keywords:
  - tenant isolation
  - docker network
  - deploy_tenant_edge_network
  - network segmentation
  - redis isolation
  - prometheus isolation
  - platform network
  - network migration
  - network breach
  - validate_tenant_network_isolation
---

# Runbook — TENANT_NETWORK_ISOLATION

Procedimiento operativo para diagnosticar, remediar y revalidar el aislamiento de red de
contenedores tenant en HostingGuard.

## Arquitectura de redes (estado correcto)

```
deploy_edge_network
  └── traefik, frontend, hosting_guard

deploy_platform_network
  └── hosting_guard, redis, prometheus, alertmanager,
      hg_worker, hg_scheduler, pgbouncer, hosting_guard_db

deploy_tenant_edge_network
  └── traefik (gateway — una sola interfaz hacia tenants), user_* (tenants)

deploy_socket_proxy_network
  └── docker_socket_proxy + servicios autorizados
```

**Invariante de aislamiento**: Un contenedor `user_*` debe aparecer **solo** en
`deploy_tenant_edge_network`. Cualquier otra red es una brecha de aislamiento.

**Constante en código**:

```python
# app/infra/docker_client.py
TENANT_NETWORK = os.getenv("TENANT_NETWORK", "deploy_tenant_edge_network")
```

## Diagnóstico rápido

```bash
# 1. Ver redes de un tenant específico
docker inspect \
  --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' \
  <CONTAINER_NAME>
# Resultado esperado:  deploy_tenant_edge_network
# Resultado anómalo:   deploy_hosting_network (brecha — red plana)
#                      deploy_platform_network (brecha — acceso a redis/prometheus)

# 2. Verificar aislamiento DNS (debe retornar vacío)
docker exec <CONTAINER_NAME> getent hosts redis
docker exec <CONTAINER_NAME> getent hosts hosting_guard
docker exec <CONTAINER_NAME> getent hosts prometheus
# → (sin output = DNS bloqueado = CORRECTO)

# 3. Verificar aislamiento TCP
docker exec <CONTAINER_NAME> \
  sh -c "nc -zw2 redis 6379 >/dev/null 2>&1 && echo OPEN || echo CLOSED"
# → CLOSED (correcto)

docker exec <CONTAINER_NAME> \
  sh -c "nc -zw2 hosting_guard 8000 >/dev/null 2>&1 && echo OPEN || echo CLOSED"
# → CLOSED (correcto)
```

## Validación completa automatizada

```bash
# Tenant específico — 25 checks de DNS + TCP + HTTP
sudo ./scripts/security/validate_tenant_network_isolation.sh <CONTAINER_NAME>

# Con verificación de que el dominio público sigue respondiendo
sudo ./scripts/security/validate_tenant_network_isolation.sh <CONTAINER_NAME> \
  --domain <subdomain>.hostingguard.lat

# Spawn de contenedor temporal en tenant_edge_network (no requiere tenant existente)
sudo ./scripts/security/validate_tenant_network_isolation.sh

# Resultado esperado:
#   Results: 25 passed, 0 failed
#   SECURE — tenant cannot reach platform services
```

## Interpretar output del script

| Output | Significado |
|---|---|
| `[PASS] DNS blocked: redis does not resolve` | Aislamiento DNS correcto |
| `[PASS] TCP blocked: redis:6379` | Aislamiento TCP correcto |
| `[PASS] HTTP blocked: hosting_guard:8000 returned 000 (curl exit=6)` | Sin respuesta HTTP — CORRECTO |
| `[FAIL] DNS resolved: redis → 172.x.x.x` | Brecha DNS — tenant ve la red de plataforma |
| `[FAIL] TCP open: redis:6379 is reachable` | Brecha TCP — tenant puede conectar |
| `[FAIL] HTTP reachable: hosting_guard:8000 returned 200` | Brecha HTTP — API interna expuesta |

> Nota: `curl exit=6` = DNS failure, `exit=7` = connection refused, `exit=28` = timeout.
> Cualquier exit != 0 con http_code `000` es PASS (no hay respuesta HTTP = servicio no reachable).

## Auditoría de todos los tenants

```bash
# Detectar tenants en redes anómalas
docker ps --filter "name=user_" --format '{{.Names}}' | while read c; do
  nets=$(docker inspect \
    --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' "$c" \
    | tr ' ' '\n' | grep -v '^$')
  unexpected=$(echo "$nets" | grep -v "^deploy_tenant_edge_network$" || true)
  if [[ -n "$unexpected" ]]; then
    echo "BREACH: $c — redes no autorizadas: $(echo $unexpected | tr '\n' ' ')"
  else
    echo "OK: $c"
  fi
done
```

## Migración de tenant a red correcta

Usar el script de migración (dry-run por defecto):

```bash
# Ver qué haría (simulación — sin cambios reales)
sudo ./scripts/ops/migrate_tenants_to_tenant_edge_network.sh

# Ejecutar migración real
sudo APPLY=true ./scripts/ops/migrate_tenants_to_tenant_edge_network.sh

# Migrar un tenant específico con validación de dominio obligatoria
sudo APPLY=true ./scripts/ops/migrate_tenants_to_tenant_edge_network.sh \
  --require-domain-validation <CONTAINER_NAME>
```

El script:
1. Detecta tenants en redes no autorizadas.
2. Verifica que el dominio público responde (pre-check).
3. Desconecta el tenant de redes no autorizadas con `docker network disconnect`.
4. Conecta a `deploy_tenant_edge_network` si no estaba ya conectado.
5. Verifica que el dominio público sigue respondiendo (post-check).
6. Hace rollback automático si el dominio falla post-migración.

## Remediación manual

Si el script no aplica o hay que migrar un solo tenant manualmente:

```bash
CONTAINER="user_1_mi-academia_a3dab0"
TENANT_NET="deploy_tenant_edge_network"

# 1. Conectar a la red correcta (si no estaba)
docker network connect "$TENANT_NET" "$CONTAINER"

# 2. Desconectar de redes no autorizadas
docker network disconnect deploy_hosting_network "$CONTAINER" 2>/dev/null || true
docker network disconnect deploy_platform_network "$CONTAINER" 2>/dev/null || true

# 3. Verificar estado final
docker inspect \
  --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' \
  "$CONTAINER"
# → deploy_tenant_edge_network (solo esta)

# 4. Revalidar
sudo ./scripts/security/validate_tenant_network_isolation.sh "$CONTAINER"
```

## Creación de nuevos tenants

Todos los paths de creación usan la constante `TENANT_NETWORK`:

| Archivo | Path de creación |
|---|---|
| `app/api/routes/hosting.py` | Static nginx, MariaDB, WordPress |
| `app/services/deploy/github_deploy_service.py` | GitHub deploy (Strategies A, B, C) |
| `app/services/router_health_guard.py` | Repair path |

En `docker run` siempre debe aparecer `"--network", TENANT_NETWORK`.

Verificación rápida del código:

```bash
# Confirmar que todos los docker run de tenants usan TENANT_NETWORK
grep -rn "TENANT_NETWORK\|tenant_edge_network" \
  app/api/routes/hosting.py \
  app/services/deploy/github_deploy_service.py \
  app/services/router_health_guard.py
```

## Señales de alarma

| Señal | Acción |
|---|---|
| `docker inspect` muestra `deploy_platform_network` en un tenant | Brecha activa — migrar inmediatamente |
| `validate_tenant_network_isolation.sh` devuelve FAIL | Escalar — verificar qué servicio es reachable |
| Tenant resuelve DNS `redis` | Red plana — aislamiento roto |
| `[FAIL] HTTP reachable: hosting_guard:8000 returned 200` | API interna expuesta |
| `[FAIL] HTTP reachable: prometheus:9090 returned 200` | Métricas internas expuestas |

## Prohibido

- No agregar tenants (`user_*`) a `deploy_platform_network`.
- No agregar tenants a `deploy_socket_proxy_network`.
- No conectar servicios de plataforma (redis, prometheus, etc.) a `deploy_tenant_edge_network`.
- No usar `--network host` en ningún tenant.
- No eliminar `TENANT_NETWORK` del comando `docker run` de ningún path de creación.

## Incidentes relacionados

- [P4B_TENANT_CAN_REACH_PLATFORM_INTERNAL_SERVICES](../incidents/P4B_TENANT_CAN_REACH_PLATFORM_INTERNAL_SERVICES.md) — Incidente original (red plana)
- [P4C_TENANT_RUNTIME_HARDENING](../security/P4C_TENANT_RUNTIME_HARDENING.md) — Runtime hardening aplicado sobre el aislamiento de red
- [VALIDATE_TENANT_NETWORK_HTTP_000_FALSE_FAIL](../incidents/VALIDATE_TENANT_NETWORK_HTTP_000_FALSE_FAIL.md) — Bug en el script de validación HTTP
