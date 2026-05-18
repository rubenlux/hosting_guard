---
type: incident
severity: medium
system: hostingguard
area: validation-script
status: resolved
rag_priority: high
keywords:
  - HTTP 000
  - curl exit code
  - false positive
  - validate_tenant_network_isolation
  - tenant isolation probe
  - curl http_code
  - false FAIL
  - 000000
  - double echo
  - curl shell
---

# VALIDATE_TENANT_NETWORK_HTTP_000_FALSE_FAIL

**Fecha detectado**: 2026-05 (validación post-P4B)
**Fecha resuelto**: 2026-05 (commit `6749177`)
**Severidad**: MEDIUM — falso positivo en script de validación (no es brecha real)
**Estado**: Resuelto

## Síntoma

`validate_tenant_network_isolation.sh` marcaba como FAIL servicios que en realidad
estaban correctamente bloqueados:

```
── App API (FastAPI) (hosting_guard:8000) ──
  [PASS] DNS blocked: hosting_guard does not resolve
  [PASS] TCP blocked: hosting_guard:8000
  [FAIL] HTTP reachable: hosting_guard:8000 returned 000000

── Prometheus (prometheus:9090) ──
  [PASS] DNS blocked: prometheus does not resolve
  [PASS] TCP blocked: prometheus:9090
  [FAIL] HTTP reachable: prometheus:9090 returned 000000
```

El código `000000` (seis ceros) no es un código HTTP válido. Los checks DNS y TCP
confirmaban que el servicio no era reachable, pero el check HTTP marcaba FAIL con un
valor imposible.

## Impacto

- Falsos positivos en el script central de validación de aislamiento de red.
- Operadores podían confundir `000000` con una brecha real de seguridad.
- La validación post-migración P4B no era confiable para el check HTTP.
- Imposible distinguir "servicio reachable" de "conexión rechazada" solo con el output.

## Evidencia

Output completo del script con el bug (servicio correctamente aislado, pero marcado FAIL):

```
── App API (FastAPI) (hosting_guard:8000) ──
  [PASS] DNS blocked: hosting_guard does not resolve
  [PASS] TCP blocked: hosting_guard:8000
  [FAIL] HTTP reachable: hosting_guard:8000 returned 000000
                                                    ^^^^^^
                                         seis ceros — código HTTP imposible
```

Los tres checks son sobre el mismo host. Si DNS no resuelve y TCP está bloqueado,
HTTP nunca puede llegar al servicio. El `000000` era un artifact del script, no
evidencia de acceso real.

## Causa raíz

### Código problemático (antes del fix)

```bash
local code
code=$(docker exec "$TENANT_CONTAINER" \
  sh -c "curl -s -o /dev/null -w '%{http_code}' --connect-timeout 2 \
         http://$ip:$port/ 2>/dev/null || echo 000")
if [[ "$code" != "000" ]]; then
  fail "HTTP reachable: $host:$port returned $code"
fi
```

### Dos bugs en la misma línea

**Bug 1 — `|| echo 000` doble-imprime**: `curl -w '%{http_code}'` **siempre** escribe
el código HTTP al stdout — incluyendo `000` cuando no hay respuesta HTTP (DNS falla,
timeout, conexión rechazada). La construcción `|| echo 000` dentro del `sh -c` solo
se ejecuta si el subshell falla, pero curl ya había escrito `000`. Resultado:
`000` (de curl) + `000` (del `echo`) = `000000`.

**Bug 2 — Decisión incorrecta**: El código verificaba solo `code != "000"`. Como
`"000000" != "000"` es verdadero, el script marcaba FAIL aunque el servicio no
fuera reachable.

### Semántica de curl que se debe conocer

| Exit code | Significado |
|---|---|
| 0 | Respuesta HTTP recibida (200, 403, 404, etc.) |
| 6 | Could not resolve host (DNS failure) |
| 7 | Failed to connect to host (connection refused) |
| 28 | Operation timed out |

La regla correcta es:
- `http_code = 000` + `exit != 0` → sin respuesta HTTP → servicio no reachable → **PASS**
- `http_code != 000` + `exit == 0` → respuesta HTTP recibida → servicio reachable → **FAIL**
- `http_code = 403/404` + `exit == 0` → servidor HTTP respondió → **FAIL** (el tenant llegó al servicio aunque reciba error)

## Fix aplicado

```bash
# FIJO — después del fix (commit 6749177)
local raw http_code curl_exit
raw=$(docker exec "$TENANT_CONTAINER" \
  sh -c "curl -s -o /dev/null -w '%{http_code}' --connect-timeout 2 \
         http://${ip}:${port}/ 2>/dev/null; printf ':%d' \$?" \
  2>/dev/null || echo "000:1")
http_code="${raw%%:*}"   # todo antes del primer colon
curl_exit="${raw##*:}"   # todo después del último colon
if [[ "$http_code" != "000" ]] && [[ "$curl_exit" == "0" ]]; then
  fail "HTTP reachable: $host:$port returned $http_code"
else
  pass "HTTP blocked: $host:$port returned $http_code (curl exit=$curl_exit)"
fi
```

**Cambios clave**:

1. `|| echo 000` eliminado — curl ya imprime el código, no se necesita fallback.
2. `; printf ':%d' \$?` captura el exit code de curl, separado por `:`.
   Usa `;` (no `||`) para que siempre se ejecute sin importar el exit de curl.
3. El output tiene formato `HTTP_CODE:EXIT_CODE` (ej: `000:6`, `403:0`).
4. FAIL solo si **ambas** condiciones son verdaderas: `http_code != "000"` **Y** `curl_exit == "0"`.
5. El `pass` ahora imprime el exit code para facilitar el diagnóstico.

**Tabla de decisiones post-fix**:

| Escenario | http_code | curl_exit | Decisión |
|---|---|---|---|
| DNS failure | `000` | `6` | PASS ✓ |
| Connection refused | `000` | `7` | PASS ✓ |
| Timeout | `000` | `28` | PASS ✓ |
| Error genérico | `000` | `1` | PASS ✓ |
| Servicio HTTP respondió 200 | `200` | `0` | FAIL ✓ |
| Servicio HTTP respondió 403 | `403` | `0` | FAIL ✓ (reachable aunque rechace) |
| Servicio HTTP respondió 404 | `404` | `0` | FAIL ✓ (reachable aunque no encuentre) |

## Validación final

Después del fix, output correcto para servicios correctamente aislados:

```
── App API (FastAPI) (hosting_guard:8000) ──
  [PASS] DNS blocked: hosting_guard does not resolve
  [PASS] TCP blocked: hosting_guard:8000
  [PASS] HTTP blocked: hosting_guard:8000 returned 000 (curl exit=6)

── Prometheus (prometheus:9090) ──
  [PASS] DNS blocked: prometheus does not resolve
  [PASS] TCP blocked: prometheus:9090
  [PASS] HTTP blocked: prometheus:9090 returned 000 (curl exit=6)

Results: 25 passed, 0 failed
SECURE — tenant cannot reach platform services
```

## Comandos de diagnóstico

```bash
# Reproducir el probe HTTP manualmente desde un tenant
docker exec <CONTAINER_NAME> \
  sh -c "curl -s -o /dev/null -w '%{http_code}' --connect-timeout 2 \
         http://hosting_guard:8000/ 2>/dev/null; printf ':%d' \$?"
# → 000:6  (DNS failure — correcto, servicio no reachable)
# → 000:7  (connection refused — correcto)
# → 200:0  (BRECHA — servicio reachable, escalar)

# Verificar ausencia del bug en el script
grep "echo 000" scripts/security/validate_tenant_network_isolation.sh
# → (sin output = fix aplicado = correcto)

# Verificar que el fix está presente
grep "printf ':%d'" scripts/security/validate_tenant_network_isolation.sh
# → sh -c "curl ... ; printf ':%d' \$?"
```

## Comandos de revalidación

```bash
# Ejecutar la validación completa con el script corregido
sudo ./scripts/security/validate_tenant_network_isolation.sh <CONTAINER_NAME>

# Confirmar que no hay salidas "000000" (seis ceros)
sudo ./scripts/security/validate_tenant_network_isolation.sh <CONTAINER_NAME> \
  2>&1 | grep "000000"
# → (sin output = sin falsos positivos)

# Verificar que servicios bloqueados aparecen como PASS con exit code informativo
sudo ./scripts/security/validate_tenant_network_isolation.sh <CONTAINER_NAME> \
  2>&1 | grep "\[PASS\].*HTTP blocked"
# Esperado: [PASS] HTTP blocked: <host>:<port> returned 000 (curl exit=6)
```

## Prevención

Tests añadidos en `tests/test_tenant_network_isolation.py`:

**Source-level** (verifican que el script tiene la implementación correcta):
- `test_http_probe_no_double_echo_000` — `|| echo 000` no existe en el script
- `test_http_probe_captures_exit_code` — `printf ':%d'` está presente
- `test_http_probe_fail_requires_both_conditions` — FAIL usa `&&` con ambas condiciones

**Behavioral** (mirror Python de la lógica bash):
- `test_http_000_nonzero_exit_is_pass` — `000 + exit 6/7/28/1` → PASS
- `test_http_dns_failure_is_pass` — exit 6 → PASS
- `test_http_timeout_is_pass` — exit 28 → PASS
- `test_http_200_is_fail` — `200 + exit 0` → FAIL
- `test_http_403_is_fail` — `403 + exit 0` → FAIL
- `test_http_404_is_fail` — `404 + exit 0` → FAIL

## Runbooks relacionados

- [TENANT_NETWORK_ISOLATION](../runbooks/TENANT_NETWORK_ISOLATION.md) — Runbook operativo de red
- [P4B_TENANT_CAN_REACH_PLATFORM_INTERNAL_SERVICES](P4B_TENANT_CAN_REACH_PLATFORM_INTERNAL_SERVICES.md) — Incidente raíz de red plana

## RAG usage

Si el operador reporta que `validate_tenant_network_isolation.sh` muestra `000000`
o FAIL en HTTP para servicios que también muestran PASS en DNS y TCP → es este bug
de doble-impresión. Verificar si el script tiene `|| echo 000` (bug) o
`; printf ':%d' \$?` (fix). Si el bug está presente, hacer `git pull` en el servidor
para obtener el commit `6749177`. Si el FAIL es con un código real (200, 403, 404)
y el DNS también resuelve → brecha real, escalar a P4B runbook.
