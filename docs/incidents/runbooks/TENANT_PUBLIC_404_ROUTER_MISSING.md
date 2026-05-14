---
incident_id: TENANT_PUBLIC_404_ROUTER_MISSING
incident_type: routing
severity: high
status: confirmed
validated: true
auto_repair_allowed: true
safe_actions:
  - regenerate_tenant_file_provider_route
forbidden_actions:
  - bypass_forwardauth_in_tenant_route
  - create_route_without_auth_middleware
signatures:
  - "404 page not found"
  - "router not found"
  - "no matching route for host"
  - "404 from traefik default backend"
---

# TENANT_PUBLIC_404_ROUTER_MISSING

## Síntoma
El subdominio de un inquilino específico (ej. `mi-academia.hostingguard.lat`) devuelve HTTP 404 cuando se accede públicamente. Otros inquilinos pueden funcionar correctamente. El 404 es devuelto por Traefik (no por la aplicación del inquilino) porque el router no existe o no se instancia.

## Impacto
- El sitio del inquilino afectado es completamente inaccesible desde internet.
- El contenedor del inquilino puede estar running y healthy — el problema está en el enrutamiento, no en el servicio.
- Un único inquilino afectado (a diferencia de `FORWARDAUTH_MIDDLEWARE_DOCKER_MISSING` que afecta a todos).

## Evidencia
```bash
# Confirmar que el 404 viene de Traefik (header Server o X-Content-Type-Options de Traefik)
curl -sv https://mi-academia.hostingguard.lat 2>&1 | grep -E "< HTTP|< Server|< X-Content"

# Verificar si el router existe en la API de Traefik
curl -sf http://localhost:8080/api/http/routers 2>/dev/null \
  | python3 -c "
import sys, json
routers = json.load(sys.stdin)
matching = [r for r in routers if 'mi-academia' in r.get('rule','')]
print('Routers encontrados:', len(matching))
for r in matching:
    print('  name:', r.get('name'))
    print('  rule:', r.get('rule'))
    print('  status:', r.get('status'))
    print('  middlewares:', r.get('middlewares'))
"

# Verificar si existe el archivo YAML del inquilino
ls -la /opt/traefik-dynamic/ | grep mi-academia
# O si todos los inquilinos están en un archivo único:
grep -n "mi-academia" /opt/traefik-dynamic/tenants-active.yml 2>/dev/null

# Verificar el contenido del YAML del inquilino
grep -A 20 "mi-academia" /opt/traefik-dynamic/tenants-active.yml 2>/dev/null

# Confirmar que el contenedor del inquilino está running
docker ps --filter "name=mi-academia" --format "{{.Names}}\t{{.Status}}\t{{.Ports}}"
```

## Causa raíz
Dos causas posibles, en orden de frecuencia:
1. **Archivo YAML ausente o entrada faltante**: La ruta del inquilino no está en `/opt/traefik-dynamic/tenants-active.yml` (o en el archivo individual del inquilino). Esto ocurre si el proceso de provisioning falló parcialmente, si el archivo fue sobreescrito sin incluir al inquilino, o si el inquilino fue desactivado manualmente sin limpiar su registro.
2. **Middleware `@docker` en el YAML**: El archivo existe y tiene la entrada del inquilino, pero el campo `middlewares` referencia `hg-forwardauth@docker` en lugar de `hg-forwardauth@file`. Traefik carga el YAML pero descarta el router porque el middleware no existe. Ver `FORWARDAUTH_MIDDLEWARE_DOCKER_MISSING.md` para contexto.

## Diagnósticos equivocados
- **"Es un problema de DNS"** — Confirmar con `dig mi-academia.hostingguard.lat` o `nslookup mi-academia.hostingguard.lat`. Si el DNS apunta al IP correcto del servidor y aun así hay 404, el problema es en Traefik, no en DNS.
- **"El contenedor del inquilino está caído"** — El contenedor puede estar perfectly running. Verificar con `docker ps`. El 404 de Traefik ocurre antes de que se intente la conexión al contenedor.
- **"La aplicación del inquilino tiene un error"** — Si el router no existe en Traefik, la aplicación nunca recibe la petición.
- **"Hay que reiniciar el contenedor del inquilino"** — El problema está en el YAML de Traefik. Reiniciar el contenedor no afecta el enrutamiento.
- **"El certificado SSL caducó"** — Un certificado caducado daría un error SSL, no un 404. Y el 404 de Traefik es explícito en la respuesta.

## Diagnóstico rápido
```bash
TENANT="mi-academia"  # ajustar según el inquilino afectado
DOMAIN="${TENANT}.hostingguard.lat"

echo "=== Diagnóstico TENANT_PUBLIC_404 para $TENANT ==="

# 1. DNS
echo "[DNS] Resolución de $DOMAIN:"
host "$DOMAIN" 2>/dev/null | head -3 || nslookup "$DOMAIN" 2>/dev/null | tail -5

# 2. HTTP response
echo "[HTTP] Respuesta de $DOMAIN:"
curl -sI "https://$DOMAIN" 2>/dev/null | head -5 || echo "  Sin respuesta HTTPS"

# 3. Router en Traefik
echo "[TRAEFIK] Buscar router para $TENANT:"
curl -sf http://localhost:8080/api/http/routers 2>/dev/null \
  | python3 -c "import sys,json; [print('  FOUND:', r['name'], 'status:', r.get('status')) for r in json.load(sys.stdin) if '$TENANT' in r.get('rule','')]" \
  2>/dev/null || echo "  No se puede acceder a API de Traefik"

# 4. YAML del inquilino
echo "[YAML] Entrada en tenants-active.yml:"
grep -A 15 "$TENANT" /opt/traefik-dynamic/tenants-active.yml 2>/dev/null || echo "  NO ENCONTRADO en tenants-active.yml"

# 5. Contenedor
echo "[DOCKER] Estado del contenedor $TENANT:"
docker ps --filter "name=$TENANT" --format "  {{.Names}}: {{.Status}}" 2>/dev/null || echo "  Contenedor no encontrado"
```

## Solución manual
```bash
TENANT="mi-academia"  # ajustar
DOMAIN="${TENANT}.hostingguard.lat"
CONTAINER_NAME="${TENANT}"  # ajustar si difiere
INTERNAL_PORT="80"  # puerto interno del contenedor (80 para nginx, 9000 para WordPress)

# CASO A: La entrada no existe en el YAML — regenerar
# Primero confirmar que no existe:
grep -q "$TENANT" /opt/traefik-dynamic/tenants-active.yml 2>/dev/null && echo "EXISTE" || echo "NO EXISTE"

# Si no existe, agregar la entrada al archivo de inquilinos activos:
# (Usar el endpoint de la API del backend para regenerar, o manualmente)

# Opción 1: Via API del backend (recomendado)
curl -X POST "http://localhost:8000/admin/tenants/${TENANT}/regenerate-route" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json"

# Opción 2: Agregar manualmente al YAML (con backup primero)
cp /opt/traefik-dynamic/tenants-active.yml /opt/traefik-dynamic/tenants-active.yml.bak.$(date +%Y%m%d_%H%M%S)

cat >> /opt/traefik-dynamic/tenants-active.yml <<EOF

  routers:
    ${TENANT}-router:
      rule: "Host(\`${DOMAIN}\`)"
      service: "${TENANT}-service"
      middlewares:
        - "hg-forwardauth@file"
      tls:
        certResolver: letsencrypt

  services:
    ${TENANT}-service:
      loadBalancer:
        servers:
          - url: "http://${CONTAINER_NAME}:${INTERNAL_PORT}"
EOF

# CASO B: La entrada existe pero usa @docker — corregir
grep -q "hg-forwardauth@docker" /opt/traefik-dynamic/tenants-active.yml && {
  echo "[FIX] Corrigiendo referencia @docker a @file"
  cp /opt/traefik-dynamic/tenants-active.yml /opt/traefik-dynamic/tenants-active.yml.bak.$(date +%Y%m%d_%H%M%S)
  sed -i 's/hg-forwardauth@docker/hg-forwardauth@file/g' /opt/traefik-dynamic/tenants-active.yml
}

# Verificar que Traefik recargó la config (esperar 2s por file watcher)
sleep 2
echo "[VERIFY] Router en Traefik:"
curl -sf http://localhost:8080/api/http/routers 2>/dev/null \
  | python3 -c "import sys,json; [print('  FOUND:', r['name'], 'status:', r.get('status')) for r in json.load(sys.stdin) if '$TENANT' in r.get('rule','')]"

echo "[VERIFY] HTTP response:"
curl -sI "https://$DOMAIN" | head -3
# Esperado: 401 o 302 (auth requerida), NO 404
```

## Fix permanente
El proceso de provisioning de inquilinos debe incluir una verificación post-escritura que confirme que:
1. La entrada del inquilino existe en el YAML de Traefik.
2. La entrada referencia `hg-forwardauth@file`.
3. Traefik ha cargado el router (verificar via API de Traefik).

El scheduler de health check debe verificar periódicamente que el número de routers activos en Traefik coincide con el número de inquilinos activos en la base de datos.

## Señales para detección automática
- Health check de ruta: `curl -sf -o /dev/null -w "%{http_code}" https://{tenant}.hostingguard.lat` retorna 404 para un inquilino activo.
- Discrepancia: inquilinos activos en DB > routers activos en API de Traefik.
- Log pattern en Traefik: `"no matching route"` o `"router not found"` para un host específico.
- El `router_health_guard.py` debe detectar 404 para inquilinos marcados como activos en la base de datos.

## Auto-remediation permitido
- Regenerar el archivo YAML del inquilino con la entrada correcta y middleware `@file` (acción: `regenerate_tenant_file_provider_route`). Esta acción es idempotente y no afecta datos del inquilino.

## Auto-remediation prohibido
- Crear una ruta para el inquilino sin el middleware `hg-forwardauth`. Esto dejaría el sitio accesible sin autenticación.
- Crear una ruta apuntando a un contenedor diferente al del inquilino (confusión de nombres).

## Dashboard esperado
- Badge **HIGH** en el panel del inquilino afectado: "Route Missing" o "Tenant Unreachable".
- En el listado global de inquilinos, el inquilino afectado muestra estado `route_missing` o `404`.
- Alerta activa en `system_incidents` con `tenant_id` del inquilino afectado.
- Panel "Router Health" muestra discrepancia entre inquilinos activos y routers en Traefik.

## RAG usage
Cuando el administrador reporte que "un inquilino específico devuelve 404", la IA debe primero verificar si el router existe en la API de Traefik, luego verificar el YAML. Si otros inquilinos funcionan normalmente, este runbook es el correcto (a diferencia de `FORWARDAUTH_MIDDLEWARE_DOCKER_MISSING` que afecta a todos). La IA debe guiar al administrador a verificar DNS primero para descartar ese falso positivo, luego revisar el YAML del inquilino.

## Tests/Chaos
```bash
#!/bin/bash
# chaos/test_tenant_404_router_missing.sh
# Simula la ausencia de ruta para un inquilino específico

set -euo pipefail

TENANT="${1:-mi-academia}"
YAML_FILE="/opt/traefik-dynamic/tenants-active.yml"
BACKUP="/tmp/${TENANT}_route_chaos_backup.yml"

echo "[CHAOS] Backup del YAML de inquilinos"
cp "$YAML_FILE" "$BACKUP"

echo "[CHAOS] Eliminar entrada del inquilino $TENANT del YAML"
# Eliminar el bloque del inquilino (simplificado — en prod usar script más robusto)
python3 -c "
import sys, re
with open('$YAML_FILE') as f:
    content = f.read()
# Eliminar sección del inquilino (aproximación)
content = re.sub(r'\s+${TENANT}-[^\n]+(\n[^\n]+)*', '', content)
with open('$YAML_FILE', 'w') as f:
    f.write(content)
print('Entrada eliminada del YAML')
" 2>/dev/null || sed -i "/$TENANT/d" "$YAML_FILE"

sleep 3

echo "[DETECT] Verificar 404 para $TENANT"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "https://${TENANT}.hostingguard.lat" 2>/dev/null || echo "000")
echo "  HTTP: $STATUS (esperado 404)"

echo "[RECOVER] Restaurar YAML original"
cp "$BACKUP" "$YAML_FILE"
sleep 3

echo "[VERIFY] Ruta restaurada"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "https://${TENANT}.hostingguard.lat" 2>/dev/null || echo "000")
echo "  HTTP: $STATUS (esperado 401 o 302, no 404)"
```
