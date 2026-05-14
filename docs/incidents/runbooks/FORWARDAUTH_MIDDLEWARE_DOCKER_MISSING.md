---
incident_id: FORWARDAUTH_MIDDLEWARE_DOCKER_MISSING
incident_type: routing
severity: critical
status: confirmed
validated: true
auto_repair_allowed: true
safe_actions:
  - regenerate_file_provider_forwardauth
  - migrate_tenant_yamls_docker_to_file
forbidden_actions:
  - disable_forwardauth_middleware
  - bypass_auth_for_tenant_routes
signatures:
  - "middleware hg-forwardauth@docker does not exist"
  - "middleware \"hg-forwardauth@docker\" does not exist"
  - "hg-forwardauth@docker: middleware not found"
---

# FORWARDAUTH_MIDDLEWARE_DOCKER_MISSING

## Síntoma
Todas las rutas de inquilinos devuelven 404 o son ignoradas por Traefik. En los logs de Traefik aparece repetidamente el mensaje `"middleware hg-forwardauth@docker does not exist"` para cada router de inquilino. El middleware de autenticación que antes estaba definido vía etiquetas Docker ya no existe porque el Docker provider fue eliminado.

## Impacto
- **Todos los inquilinos activos están inaccesibles** — sus subdominios retornan 404 o son descartados por Traefik antes de llegar al contenedor.
- El sistema de autenticación de inquilinos (ForwardAuth hacia el backend FastAPI) no puede ser invocado.
- No hay riesgo de bypass de autenticación — Traefik rechaza las rutas por completo al no encontrar el middleware, no las deja pasar sin auth.
- Impacto total en todas las rutas que referencian `hg-forwardauth@docker`.

## Evidencia
```bash
# Confirmar el error exacto en logs de Traefik
docker compose -f /opt/deploy/docker-compose.yml logs --tail=100 traefik 2>&1 | grep -i "middleware\|forwardauth\|does not exist"

# Listar los middlewares actualmente disponibles en Traefik via API
curl -sf http://localhost:8080/api/http/middlewares 2>/dev/null | python3 -m json.tool | grep -E '"name"|"provider"'

# Verificar si el archivo de definición del middleware existe
ls -la /opt/traefik-dynamic/tenant-forwardauth-middleware.yml 2>/dev/null || echo "ARCHIVO NO EXISTE"

# Ver qué middleware referencian los YAMLs de inquilinos activos
grep -r "forwardauth" /opt/traefik-dynamic/ 2>/dev/null

# Contar cuántos YAMLs de inquilinos aún referencian @docker
grep -rl "hg-forwardauth@docker" /opt/traefik-dynamic/ 2>/dev/null | wc -l
```
Salida esperada del error:
```
time="..." level=error msg="middleware hg-forwardauth@docker does not exist"
time="..." level=error msg="error instantiating router..." error="middleware hg-forwardauth@docker does not exist"
```

## Causa raíz
El middleware `hg-forwardauth` estaba originalmente definido vía etiqueta Docker en el contenedor del backend FastAPI (ej. `traefik.http.middlewares.hg-forwardauth.forwardauth.address=http://app:8000/auth/verify`). Al eliminar el Docker provider de Traefik (fix para `TRAEFIK_DOCKER_PROVIDER_UNHEALTHY`), el middleware `hg-forwardauth@docker` dejó de existir. Todos los archivos YAML de inquilinos en `/opt/traefik-dynamic/` seguían referenciando `hg-forwardauth@docker`, que ya no está registrado en ningún provider. Traefik descarta los routers que referencian middlewares inexistentes.

## Diagnósticos equivocados
- **"El backend FastAPI está caído"** — El backend puede estar perfectamente healthy. El problema está en Traefik, no en el servicio destino.
- **"Los contenedores de inquilinos están caídos"** — Los contenedores están running. Traefik ni siquiera les envía tráfico porque descarta el router antes de hacer forward.
- **"Es un problema de DNS"** — DNS resuelve correctamente al IP del servidor. El 404 lo devuelve Traefik porque el router no se instancia.
- **"Hay que reiniciar los contenedores de inquilinos"** — Inútil. El problema está en la definición del middleware en el file provider de Traefik.
- **"El archivo YAML del inquilino está corrupto"** — El YAML puede ser sintácticamente correcto; el problema es la referencia al middleware `@docker` que ya no existe.

## Diagnóstico rápido
```bash
# 1. Confirmar el error de middleware en Traefik
docker compose -f /opt/deploy/docker-compose.yml logs --tail=50 traefik 2>&1 | grep "does not exist\|middleware"

# 2. Verificar si hg-forwardauth está disponible en algún provider
curl -sf http://localhost:8080/api/http/middlewares 2>/dev/null \
  | python3 -c "import sys,json; data=json.load(sys.stdin); print([m['name'] for m in data])" 2>/dev/null \
  || echo "No se puede acceder a la API de Traefik"

# 3. Verificar si el archivo de middleware file provider existe
test -f /opt/traefik-dynamic/tenant-forwardauth-middleware.yml \
  && echo "EXISTE: $(cat /opt/traefik-dynamic/tenant-forwardauth-middleware.yml)" \
  || echo "NO EXISTE: /opt/traefik-dynamic/tenant-forwardauth-middleware.yml"

# 4. Contar YAMLs que aún usan @docker
echo "YAMLs con @docker:"
grep -rl "@docker" /opt/traefik-dynamic/ 2>/dev/null

echo "YAMLs con @file:"
grep -rl "@file" /opt/traefik-dynamic/ 2>/dev/null
```

## Solución manual
```bash
# PASO 1: Crear el archivo de definición del middleware via file provider
cat > /opt/traefik-dynamic/tenant-forwardauth-middleware.yml <<'EOF'
http:
  middlewares:
    hg-forwardauth:
      forwardAuth:
        address: "http://app:8000/auth/verify"
        authResponseHeaders:
          - "X-User-Id"
          - "X-User-Email"
          - "X-Tenant-Id"
        trustForwardHeader: true
EOF

# PASO 2: Verificar que Traefik cargó el middleware (esperar ~2s por el file watcher)
sleep 2
curl -sf http://localhost:8080/api/http/middlewares 2>/dev/null \
  | python3 -c "import sys,json; data=json.load(sys.stdin); [print(m['name']) for m in data if 'forwardauth' in m['name'].lower()]"

# PASO 3: Migrar todos los YAMLs de inquilinos de @docker a @file
# Buscar todos los archivos afectados
FILES=$(grep -rl "hg-forwardauth@docker" /opt/traefik-dynamic/ 2>/dev/null)
echo "Archivos a migrar: $FILES"

# Hacer backup
for f in $FILES; do
  cp "$f" "${f}.bak.$(date +%Y%m%d_%H%M%S)"
done

# Aplicar la migración
for f in $FILES; do
  sed -i 's/hg-forwardauth@docker/hg-forwardauth@file/g' "$f"
  echo "Migrado: $f"
done

# PASO 4: Verificar que ya no quedan referencias a @docker
REMAINING=$(grep -rl "hg-forwardauth@docker" /opt/traefik-dynamic/ 2>/dev/null | wc -l)
echo "Referencias @docker restantes: $REMAINING (debe ser 0)"

# PASO 5: Verificar que Traefik instancia los routers correctamente
sleep 3
docker compose -f /opt/deploy/docker-compose.yml logs --tail=20 traefik 2>&1 | grep -v "does not exist"

# PASO 6: Probar acceso a un inquilino
curl -I https://mi-academia.hostingguard.lat 2>/dev/null | head -5
# Esperado: 401 (el middleware existe y rechaza sin auth) o redirect al login
# NO esperado: 404
```

## Fix permanente
Generar el archivo `/opt/traefik-dynamic/tenant-forwardauth-middleware.yml` como parte del proceso de bootstrap del servidor. Este archivo debe ser creado por el script de instalación inicial y debe existir antes de que cualquier inquilino sea creado. El proceso de generación de rutas de inquilinos (función `write_tenant_traefik_config` en el backend) debe siempre usar `hg-forwardauth@file` como referencia de middleware.

Agregar una validación en el scheduler/health check que detecte si algún YAML de inquilino referencia `@docker` cuando el Docker provider está desactivado.

## Señales para detección automática
- Log pattern: `"middleware.*@docker.*does not exist"` en contenedor traefik
- Verificación periódica: `grep -rl "@docker" /opt/traefik-dynamic/` devuelve archivos
- Health check de middleware: `curl -sf http://localhost:8080/api/http/middlewares | grep -c "hg-forwardauth"` == 0
- Alerta: todas las rutas de inquilinos devuelven 404 simultáneamente (correlación de errores)

## Auto-remediation permitido
- Crear `/opt/traefik-dynamic/tenant-forwardauth-middleware.yml` si no existe (acción: `regenerate_file_provider_forwardauth`). Es una operación de escritura segura que no modifica datos de inquilinos.
- Migrar YAMLs de inquilinos de `@docker` a `@file` (acción: `migrate_tenant_yamls_docker_to_file`). Debe hacerse sólo después de confirmar que el archivo de definición del middleware existe.

## Auto-remediation prohibido
- Deshabilitar el middleware `hg-forwardauth` en las rutas de inquilinos para "resolver" el 404. Esto dejaría las rutas sin autenticación.
- Crear rutas de inquilinos sin middleware de autenticación como medida temporal.
- Eliminar YAMLs de inquilinos sin backup previo.

## Dashboard esperado
- Badge **CRITICAL** en el panel "Tenant Routes" del dashboard de administración.
- Todos los inquilinos activos muestran estado `unavailable` o `404` en el panel de salud de rutas.
- Alerta activa: `"ForwardAuth middleware missing — all tenant routes down"`.
- Panel de Traefik health muestra 0 routers activos de inquilinos.

## RAG usage
Cuando el administrador reporte que "todos los inquilinos devuelven 404 al mismo tiempo", "el middleware no existe" o "hg-forwardauth@docker not found", este runbook es el primero a consultar. La IA debe verificar si el archivo `/opt/traefik-dynamic/tenant-forwardauth-middleware.yml` existe y si los YAMLs de inquilinos referencian `@docker` o `@file`. Si el problema ocurrió justo después de eliminar el Docker provider de Traefik, confirmar con `TRAEFIK_DOCKER_PROVIDER_UNHEALTHY.md` como causa raíz. La solución de auto-remediación es segura si el middleware address del backend es correcto.

## Tests/Chaos
```bash
#!/bin/bash
# chaos/test_forwardauth_middleware_missing.sh
# Simula la ausencia del middleware file provider y verifica detección + recuperación

set -euo pipefail

MIDDLEWARE_FILE="/opt/traefik-dynamic/tenant-forwardauth-middleware.yml"
BACKUP="/tmp/tenant-forwardauth-middleware.yml.chaos_backup"

echo "[CHAOS] Backup del middleware file"
cp "$MIDDLEWARE_FILE" "$BACKUP"

echo "[CHAOS] Eliminar el middleware file"
rm -f "$MIDDLEWARE_FILE"
sleep 3

echo "[DETECT] Verificar error en Traefik logs"
if docker compose -f /opt/deploy/docker-compose.yml logs --tail=30 traefik 2>&1 | grep -q "does not exist"; then
  echo "[OK] Error detectado: middleware no encontrado"
else
  echo "[WARN] Error no detectado — verificar si los YAMLs ya usan @file"
fi

echo "[DETECT] Verificar que inquilinos retornan 404"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://mi-academia.hostingguard.lat 2>/dev/null || echo "000")
echo "  HTTP status de mi-academia: $STATUS (esperado 404)"

echo "[RECOVER] Restaurar middleware file"
cp "$BACKUP" "$MIDDLEWARE_FILE"
sleep 3

echo "[VERIFY] El middleware debe estar disponible"
curl -sf http://localhost:8080/api/http/middlewares 2>/dev/null \
  | python3 -c "import sys,json; data=json.load(sys.stdin); mws=[m['name'] for m in data]; print('forwardauth presente:', any('forwardauth' in m for m in mws))"

echo "[VERIFY] Inquilino debe responder (401 o redirect, no 404)"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://mi-academia.hostingguard.lat 2>/dev/null || echo "000")
echo "  HTTP status de mi-academia: $STATUS (esperado: 401 o 302, no 404)"
```
