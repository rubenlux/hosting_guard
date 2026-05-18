---
type: security-hardening
severity: high
system: hostingguard
area: tenant-runtime
status: resolved
rag_priority: high
keywords:
  - no-new-privileges
  - pids-limit
  - memory limit
  - cpu limit
  - read-only mount
  - docker.sock
  - socket_proxy_network
  - runtime hardening
  - tenant container
  - privileged
  - fork bomb
  - resource exhaustion
  - tenant_hardening_flags
---

# P4C — Tenant Runtime Hardening

**Fecha**: 2026-05 (auditoría P4C)
**Estado**: Aplicado y validado en producción

## Síntoma

Los contenedores tenant (`user_*`) existentes carecían de controles de runtime que
limitan el impacto potencial de un tenant comprometido:

- Sin `--security-opt no-new-privileges:true` → un proceso dentro del tenant podía
  ganar privilegios vía setuid o sudo si el binario estaba disponible.
- Sin `--pids-limit` → posible fork bomb que agotara PIDs del host, afectando todos
  los tenants del servidor.
- Sin límites de memoria → un tenant podía consumir toda la RAM del host.
- Sin límites de CPU → un tenant podía monopolizar CPU, degradando todos los demás.
- Mount del sitio sin `:ro` → el tenant podía modificar sus propios binarios en el
  bind mount compartido con el host.

## Impacto (pre-hardening)

- Un tenant comprometido podía ejecutar procesos setuid para escalar privilegios.
- Fork bomb podía tumbar el host entero, afectando los 6 tenants del servidor.
- Un tenant malicioso podía provocar DoS de recursos (RAM/CPU) al resto.
- Sin `:ro` en el mount nginx, un adversario con escritura en el contenedor podía
  alterar archivos que persisten en el host.

## Evidencia (estado pre-hardening)

```
validate_runtime_hardening.sh — ANTES del fix:

Results: 36 passed, 18 warnings, 0 failures

  [WARN] no-new-privileges not set  ← 6 contenedores
  [WARN] No pids limit              ← contenedor creado antes de la política
  [WARN] No memory limit            ← ídem
  [WARN] No cpu quota               ← ídem
```

## Causa raíz

Los flags de hardening no estaban incluidos en ningún path de `docker run` de la
plataforma. Los contenedores existentes no tenían estos flags porque fueron creados
antes de esta política y no había script para recrearlos con los nuevos parámetros.

Adicionalmente, el script `validate_runtime_hardening.sh` tenía un bug: `PidsLimit`,
`Memory` y `NanoCpus` son `null` en el JSON de `docker inspect` cuando no están
configurados. `dict.get('PidsLimit', 0)` en Python retorna `None` (no `0`) cuando el
valor JSON es `null`, y `print(None)` imprime la cadena `"None"` (con N mayúscula).
La comparación bash `== "null"` no hacía match, por lo que el WARN no se emitía.

## Fix aplicado

### 1. Nueva función central en `app/infra/docker_client.py`

```python
TENANT_PIDS_LIMIT = int(os.getenv("TENANT_PIDS_LIMIT", "200"))

def tenant_hardening_flags() -> list[str]:
    """Flags de seguridad y límites de recursos para cada docker run de tenant.
    Usar como: *tenant_hardening_flags() dentro de la lista de comandos.
    """
    return [
        "--security-opt", "no-new-privileges:true",
        "--pids-limit",   str(TENANT_PIDS_LIMIT),
    ]
```

### 2. Flags aplicados en todos los paths de creación de tenants

`*tenant_hardening_flags()` agregado en:

| Archivo | Paths cubiertos |
|---|---|
| `app/api/routes/hosting.py` | Static nginx, MariaDB, WordPress |
| `app/services/deploy/github_deploy_service.py` | Strategy A (Dockerfile), B (app server), C-nginx, C-static |
| `app/services/router_health_guard.py` | Repair path |

Junto con flags que ya existían por plan de recursos:
- `--memory <N>m` — límite de RAM
- `--cpus <N>` — límite de CPU
- `:ro` en bind mount nginx — sitio read-only

### 3. Corrección del bug Python None → "None" en validate_runtime_hardening.sh

**Antes (buggy)**:

```bash
PIDS=$(echo "$HOST_CFG" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(d.get('PidsLimit', 0))  # retorna None si el JSON tiene null
" 2>/dev/null || echo "0")
if [[ "$PIDS" == "null" ]]; then  # nunca hace match con "None"
    warn "No pids limit"
fi
```

**Después (corregido)**:

```bash
PIDS=$(echo "$HOST_CFG" | python3 -c "
import json,sys
d=json.load(sys.stdin)
v=d.get('PidsLimit')
print(0 if not v or v <= 0 else int(v))
" 2>/dev/null || echo "0")
if [[ "$PIDS" -le 0 ]]; then
    warn "No pids limit — fork-bomb possible (add --pids-limit)"
else
    pass "pids limit: $PIDS"
fi
```

El mismo patrón se aplicó para `Memory` y `NanoCpus`. Todos usan `-le 0` numérico.

### 4. Script de hardening para contenedores existentes

`scripts/ops/harden_existing_tenants.sh` — recrea cada tenant existente con los
nuevos flags, preservando configuración original:

```bash
# Simulación (dry-run por defecto — sin cambios)
sudo ./scripts/ops/harden_existing_tenants.sh

# Aplicar hardening real
sudo APPLY=true ./scripts/ops/harden_existing_tenants.sh
```

El script preserva:
- Red: `deploy_tenant_edge_network`
- Mounts: bind mounts originales, incluyendo `:ro`
- Variables de entorno: escritas a archivo temporal (`--env-file`), nunca impresas
- Imagen y comando originales

Tiene rollback automático: si el dominio público no responde tras recrear, restaura
el contenedor con la configuración original.

## Validación final

```bash
sudo ./scripts/security/validate_runtime_hardening.sh

# Resultado obtenido (6 tenants):
#   Results: 54 passed, 0 warnings, 0 failures
#   SECURE — all tenant containers passed runtime hardening checks
```

## Comandos de diagnóstico

```bash
# Ver flags de un tenant específico
docker inspect --format \
  '{{.HostConfig.SecurityOpt}} | pids={{.HostConfig.PidsLimit}} | mem={{.HostConfig.Memory}} | cpu={{.HostConfig.NanoCpus}}' \
  <CONTAINER_NAME>
# Esperado: [no-new-privileges:true] | pids=200 | mem=<N> | cpu=<N>

# Verificar que NO es privileged
docker inspect --format '{{.HostConfig.Privileged}}' <CONTAINER_NAME>
# → false

# Verificar que NO tiene docker.sock montado
docker inspect --format '{{.HostConfig.Binds}}' <CONTAINER_NAME> | tr ' ' '\n' \
  | grep docker.sock
# → (sin output = correcto)

# Verificar que NO está en socket_proxy_network
docker inspect \
  --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' \
  <CONTAINER_NAME> | tr ' ' '\n' | grep socket_proxy
# → (sin output = correcto)

# Verificar mount read-only del sitio nginx
docker inspect --format '{{.HostConfig.Binds}}' <CONTAINER_NAME> | tr ' ' '\n' \
  | grep "nginx/html.*:ro"
# → /opt/clients/.../html:/usr/share/nginx/html:ro
```

## Comandos de revalidación

```bash
# Validación completa de todos los tenants
sudo ./scripts/security/validate_runtime_hardening.sh

# Validación de un tenant específico
sudo ./scripts/security/validate_runtime_hardening.sh --tenant <CONTAINER_NAME>

# Resultado limpio esperado:
#   Results: N passed, 0 warnings, 0 failures
#   SECURE — all tenant containers passed runtime hardening checks
```

## Checklist de hardening por contenedor

| Check | Configuración | Nivel si incumple |
|---|---|---|
| No privileged | `Privileged: false` | FAIL — crítico |
| No docker.sock mount | Sin `/var/run/docker.sock` en Binds | FAIL — crítico |
| No socket_proxy_network | Sin `deploy_socket_proxy_network` en Networks | FAIL — crítico |
| Solo tenant_edge_network | Solo `deploy_tenant_edge_network` en Networks | WARN |
| no-new-privileges | `--security-opt no-new-privileges:true` en SecurityOpt | WARN |
| pids-limit | `PidsLimit >= 1` (default: 200) | WARN |
| Memory limit | `Memory > 0` | WARN |
| CPU limit | `NanoCpus > 0` | WARN |
| Site mount `:ro` | `:ro` en bind mount nginx html | WARN |

Los checks FAIL son violaciones de seguridad que impiden que el script salga con código 0.
Los checks WARN son configuraciones subóptimas que deben resolverse recreando el contenedor.

## Rollback conceptual

Si un contenedor recreado con hardening presenta problemas:

1. El script `harden_existing_tenants.sh` hace rollback automático si el dominio falla post-recreación.
2. Para rollback manual: identificar configuración original con `docker inspect` (del backup del script) y recrear sin los flags nuevos.
3. Investigar la causa del fallo antes de rehacer el hardening.
4. Nunca dejar un tenant en producción sin `no-new-privileges` y `pids-limit` como estado permanente.

## Prevención

1. `tenant_hardening_flags()` es la fuente de verdad — toda creación de tenant debe incluir `*tenant_hardening_flags()`.
2. Ejecutar `validate_runtime_hardening.sh` después de cualquier cambio en paths de `docker run`.
3. Tests de cobertura en `tests/test_tenant_network_isolation.py`:
   - `test_tenant_hardening_flags_exported`
   - `test_tenant_pids_limit_exported`
   - `test_hosting_py_static_includes_security_opt`
   - `test_github_deploy_includes_security_opt`
   - `test_router_health_guard_includes_security_opt`
   - `test_no_tenant_creation_uses_privileged`
   - `test_no_tenant_creation_mounts_docker_sock`
   - `test_validate_pids_none_normalized_before_comparison`
   - `test_validate_numeric_comparisons_no_null_strings`

## Runbooks relacionados

- [TENANT_NETWORK_ISOLATION](../runbooks/TENANT_NETWORK_ISOLATION.md) — Aislamiento de red (P4B, prerequisito)
- [P4B_TENANT_CAN_REACH_PLATFORM_INTERNAL_SERVICES](../incidents/P4B_TENANT_CAN_REACH_PLATFORM_INTERNAL_SERVICES.md) — Incidente de red plana previo

## RAG usage

Cuando el operador reporte que `validate_runtime_hardening.sh` muestra WARNs por
`no-new-privileges`, `pids-limit`, `memory` o `cpu` ausentes → usar `harden_existing_tenants.sh`
para recrear los contenedores con los flags correctos. Si hay FAILs (privileged, docker.sock,
socket_proxy_network) → intervención inmediata, no usar el script de hardening sino investigar
si hubo cambios no autorizados en la configuración del contenedor.
