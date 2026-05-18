---
type: incident
severity: critical
system: hostingguard
area: docker-networking
status: resolved
rag_priority: high
keywords:
  - tenant isolation
  - docker network
  - redis
  - hosting_guard
  - prometheus
  - alertmanager
  - flat network
  - deploy_hosting_network
  - tenant_edge_network
  - network breach
  - platform internal services
---

# P4B — TENANT_CAN_REACH_PLATFORM_INTERNAL_SERVICES

**Fecha detectado**: 2026-04 (auditoría de seguridad P4B)
**Fecha resuelto**: 2026-04 (segmentación de redes aplicada)
**Severidad**: CRITICAL
**Estado**: Resuelto

## Síntoma

Un tenant (contenedor `user_*`) podía resolver por DNS y conectar vía TCP/HTTP a servicios
internos de la plataforma desde dentro de su contenedor:

- `redis:6379` — token store, datos de sesión, caché
- `hosting_guard:8000` — API interna FastAPI
- `prometheus:9090` — métricas internas de la plataforma
- `alertmanager:9093` — gestión de alertas

Cualquier tenant podía ejecutar desde su contenedor:

```bash
# Dentro del tenant — esto NO debería funcionar
nc -zw2 redis 6379            # → OPEN
curl http://hosting_guard:8000/  # → HTTP 200/401
curl http://prometheus:9090/metrics  # → HTTP 200 con métricas internas
```

## Impacto

- **Confidencialidad**: Los tenants podían leer métricas internas de la plataforma
  (Prometheus expone contadores de todos los tenants, Alertmanager expone reglas de alerta).
- **Escalada de privilegios**: Con acceso al API interno (`hosting_guard:8000`) un tenant podía
  intentar bypasses de autenticación o explorar endpoints no expuestos públicamente.
- **Riesgo de exfiltración**: Redis expuesto podía permitir lectura de tokens JWT, sesiones de
  otros usuarios, o datos de caché de la plataforma.
- **Aislamiento multi-tenant roto**: Un tenant comprometido tenía visibilidad de red sobre la
  infraestructura entera de la plataforma y potencialmente sobre otros tenants.

## Evidencia

Validación ejecutada desde un contenedor tenant (`user_1_mi-academia_a3dab0`) antes del fix:

```
── Redis (token store) (redis:6379) ──
  [FAIL] DNS resolved: redis → 172.20.0.5
  [FAIL] TCP open: redis:6379 is reachable

── App API (FastAPI) (hosting_guard:8000) ──
  [FAIL] DNS resolved: hosting_guard → 172.20.0.3
  [FAIL] TCP open: hosting_guard:8000 is reachable
  [FAIL] HTTP reachable: hosting_guard:8000 returned 200

── Prometheus (prometheus:9090) ──
  [FAIL] DNS resolved: prometheus → 172.20.0.8
  [FAIL] HTTP reachable: prometheus:9090 returned 200

── Alertmanager (alertmanager:9093) ──
  [FAIL] DNS resolved: alertmanager → 172.20.0.9
  [FAIL] HTTP reachable: alertmanager:9093 returned 200

Results: 4 passed, 12 failed — CRITICAL
```

## Causa raíz

Todos los servicios de la plataforma y los contenedores tenant compartían **una única red
Docker plana**: `hosting_network` / `deploy_hosting_network`.

En una red Docker flat, todos los contenedores se resuelven entre sí por nombre de servicio
y pueden conectar a cualquier puerto expuesto en esa red, sin restricción de ningún tipo.

Arquitectura original (incorrecta):

```
deploy_hosting_network (red plana — TODO compartido):
  ├── traefik
  ├── hosting_guard   ← API interna con endpoints privilegiados
  ├── redis           ← token store, sesiones JWT
  ├── prometheus      ← métricas internas de la plataforma
  ├── alertmanager    ← alertas de la plataforma
  ├── hg_worker
  ├── hg_scheduler
  ├── pgbouncer
  ├── hosting_guard_db
  └── user_1_mi-academia_a3dab0  ← tenant con visibilidad total
```

## Fix aplicado

Separación en 4 redes Docker con visibilidad explícita y mínima:

| Red | Servicios | Visible al tenant |
|---|---|---|
| `deploy_edge_network` | traefik, frontend, hosting_guard | No |
| `deploy_platform_network` | hosting_guard, redis, prometheus, alertmanager, hg_worker, hg_scheduler, pgbouncer, hosting_guard_db | No |
| `deploy_tenant_edge_network` | traefik (gateway solamente), `user_*` | Sí — solo esta red |
| `deploy_socket_proxy_network` | docker_socket_proxy + servicios autorizados | No |

Los tenants quedaron **exclusivamente** en `deploy_tenant_edge_network`. Traefik actúa como
gateway, conectado a `deploy_edge_network` + `deploy_tenant_edge_network`, sin exponer la red
de plataforma hacia los tenants.

**Archivos de producción modificados** (en `/opt/deploy/` en el servidor — no en git):
- `docker-compose.yml` — definición de redes y asignación de servicios por red

**Código modificado** (en git):
- `app/infra/docker_client.py` — constante `TENANT_NETWORK = os.getenv("TENANT_NETWORK", "deploy_tenant_edge_network")`
- `app/api/routes/hosting.py` — `--network $TENANT_NETWORK` en toda creación de tenant
- `app/services/deploy/github_deploy_service.py` — ídem para deploys desde GitHub
- `app/services/router_health_guard.py` — ídem para repair path

**Script de migración**: `scripts/ops/migrate_tenants_to_tenant_edge_network.sh`

## Validación final

```bash
sudo ./scripts/security/validate_tenant_network_isolation.sh user_1_mi-academia_a3dab0

# Resultado obtenido:
#   Container is on deploy_tenant_edge_network  ✓
#   Container is on tenant_edge_network ONLY    ✓
#   [PASS] DNS blocked: redis does not resolve
#   [PASS] TCP blocked: redis:6379
#   [PASS] DNS blocked: hosting_guard does not resolve
#   [PASS] TCP blocked: hosting_guard:8000
#   [PASS] HTTP blocked: hosting_guard:8000 returned 000 (curl exit=6)
#   [PASS] DNS blocked: prometheus does not resolve
#   [PASS] HTTP blocked: prometheus:9090 returned 000 (curl exit=6)
#   [PASS] DNS blocked: alertmanager does not resolve
#   [PASS] HTTP blocked: alertmanager:9093 returned 000 (curl exit=6)
#   [PASS] DNS blocked: docker_socket_proxy does not resolve
#   [PASS] TCP blocked: docker_socket_proxy:2375
#   [PASS] DNS blocked: pgbouncer does not resolve
#   [PASS] TCP blocked: pgbouncer:5432
#   Results: 25 passed, 0 failed
#   SECURE — tenant cannot reach platform services
```

## Comandos de diagnóstico

```bash
# Ver redes de un tenant específico
docker inspect \
  --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' \
  user_1_mi-academia_a3dab0
# Esperado: deploy_tenant_edge_network
# Anómalo:  deploy_hosting_network (red plana — brecha)

# Verificar que el tenant NO resuelve redis por DNS
docker exec user_1_mi-academia_a3dab0 getent hosts redis
# → (sin output = DNS bloqueado = CORRECTO)

# Verificar aislamiento TCP a redis
docker exec user_1_mi-academia_a3dab0 \
  sh -c "nc -zw2 redis 6379 >/dev/null 2>&1 && echo OPEN || echo CLOSED"
# → CLOSED (correcto)

# Verificar aislamiento TCP al API interno
docker exec user_1_mi-academia_a3dab0 \
  sh -c "nc -zw2 hosting_guard 8000 >/dev/null 2>&1 && echo OPEN || echo CLOSED"
# → CLOSED (correcto)

# Auditar redes de todos los tenants en un solo comando
docker ps --filter "name=user_" --format '{{.Names}}' | while read c; do
  nets=$(docker inspect \
    --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' "$c")
  unexpected=$(echo "$nets" | tr ' ' '\n' | grep -v "^deploy_tenant_edge_network$" | grep -v "^$" || true)
  if [[ -n "$unexpected" ]]; then
    echo "BREACH: $c — también en: $unexpected"
  else
    echo "OK: $c"
  fi
done
```

## Comandos de revalidación

```bash
# Validación completa de aislamiento (tenant específico)
sudo ./scripts/security/validate_tenant_network_isolation.sh <CONTAINER_NAME>

# Con verificación de acceso público (confirma que el tenant sigue funcionando)
sudo ./scripts/security/validate_tenant_network_isolation.sh <CONTAINER_NAME> \
  --domain <subdomain>.hostingguard.lat

# Spawn de contenedor temporal (prueba la red sin tenant existente)
sudo ./scripts/security/validate_tenant_network_isolation.sh

# Auditar todos los tenants (redes anómalas)
docker ps --filter "name=user_" --format '{{.Names}}' | while read c; do
  nets=$(docker inspect \
    --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' "$c" \
    | tr ' ' '\n' | grep -v '^$')
  unexpected=$(echo "$nets" | grep -v "^deploy_tenant_edge_network$" || true)
  [[ -n "$unexpected" ]] && echo "BREACH: $c: $unexpected" || echo "OK: $c"
done
```

## Rollback conceptual

Si la segmentación rompe conectividad legítima de algún servicio de plataforma:

1. Identificar qué servicio necesita acceso a qué red.
2. Agregar ese servicio a la red correcta en `docker-compose.yml` (en `/opt/deploy/`).
3. Recrear el servicio: `docker compose up -d --no-deps <service>`.
4. **Nunca** agregar tenants (`user_*`) a `deploy_platform_network`.
5. Si un tenant necesita datos de la plataforma, exponer vía API pública con autenticación.

## Prevención

1. Todo nuevo tenant debe crearse con `--network $TENANT_NETWORK` (constante en `docker_client.py`).
2. Ejecutar `validate_tenant_network_isolation.sh` después de cualquier cambio en topología de redes.
3. No agregar nuevos servicios de plataforma a `deploy_tenant_edge_network`.
4. Tests de cobertura en `tests/test_tenant_network_isolation.py`:
   - `test_new_tenants_not_on_platform_network`
   - `test_new_tenants_not_on_edge_network`

## Runbooks relacionados

- [TENANT_NETWORK_ISOLATION](../runbooks/TENANT_NETWORK_ISOLATION.md) — Procedimiento operativo completo de red
- [P4C_TENANT_RUNTIME_HARDENING](../security/P4C_TENANT_RUNTIME_HARDENING.md) — Hardening adicional aplicado tras P4B

## RAG usage

Cuando el operador reporte que un tenant puede acceder a servicios internos, ver métricas de
Prometheus, conectar a Redis, o alcanzar el API de la plataforma desde su contenedor →
este es el incidente raíz. La causa es una red Docker plana. Verificar redes del contenedor
con `docker inspect`. El fix es migrar a `deploy_tenant_edge_network` exclusivamente y separar
servicios de plataforma a `deploy_platform_network`. Ejecutar `validate_tenant_network_isolation.sh`
para confirmar el estado de aislamiento.
