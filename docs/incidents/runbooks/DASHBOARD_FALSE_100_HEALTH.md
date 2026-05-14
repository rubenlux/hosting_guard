---
incident_id: DASHBOARD_FALSE_100_HEALTH
incident_type: observability
severity: high
status: confirmed
validated: true
auto_repair_allowed: false
safe_actions: []
forbidden_actions:
  - mark_incident_healthy_on_200_without_body_check
  - auto_resolve_router_health_incidents
signatures:
  - "dashboard shows 100% healthy"
  - "HTTP 200 + Welcome to nginx"
  - "false positive health check"
  - "status: healthy despite nginx default page"
  - "body_check: disabled"
---

# DASHBOARD_FALSE_100_HEALTH

## Síntoma
El dashboard de administración muestra "100% de rutas saludables" o todos los inquilinos con estado "healthy/verde", mientras que en realidad uno o más inquilinos están sirviendo la página por defecto de nginx ("Welcome to nginx!") en lugar del contenido real. El sistema de salud confía en el código HTTP 200 como único indicador de salud, lo que produce un falso positivo.

## Impacto
- El administrador no tiene visibilidad real del estado de los sitios de inquilinos.
- Un inquilino puede estar experimentando pérdida total de contenido sin que el sistema lo detecte ni alerte.
- La confianza en el dashboard se erosiona: si el dashboard dice "todo bien" y el cliente llama reportando el problema, el sistema de monitoreo ha fallado.
- El SLA del inquilino se está incumpliendo aunque el dashboard no lo muestre.
- Los incidentes generados por `router_health_guard.py` son críticos y no deben ser auto-resueltos.

## Evidencia
```bash
# Confirmar el falso positivo: verificar el contenido real de un inquilino "healthy"
TENANT="mi-academia"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "https://${TENANT}.hostingguard.lat")
BODY=$(curl -sf "https://${TENANT}.hostingguard.lat" 2>/dev/null | head -5)

echo "HTTP code: $HTTP_CODE"
echo "Body preview: $BODY"

if [ "$HTTP_CODE" = "200" ] && echo "$BODY" | grep -qi "welcome to nginx"; then
  echo "[FALSE POSITIVE] HTTP 200 pero sirve nginx default page"
fi

# Ver los parámetros del health check actual
curl -sf "http://localhost:8000/admin/router-health/config" \
  -H "Authorization: Bearer $ADMIN_TOKEN" 2>/dev/null | python3 -m json.tool

# Ver el estado del dashboard tal como lo ve el sistema
curl -sf "http://localhost:8000/admin/dashboard/health-summary" \
  -H "Authorization: Bearer $ADMIN_TOKEN" 2>/dev/null | python3 -m json.tool

# Buscar si hay incidentes de router_health_guard activos
docker exec -i hg_db psql -U hguser -d hostingguard -c \
  "SELECT id, tenant_id, incident_type, severity, status, source_table, created_at
   FROM system_incidents
   WHERE source_table = 'router_health_guard'
   AND status = 'open'
   ORDER BY created_at DESC LIMIT 10;"
```

## Causa raíz
El sistema de health check de rutas (`router_health_guard.py`) verificaba únicamente el código de respuesta HTTP. Si el código era 200, el sitio se marcaba como "healthy". La página por defecto de nginx devuelve HTTP 200 con un cuerpo HTML de ~600 bytes que contiene `"Welcome to nginx!"`. Esta cadena identifica de forma unívoca que nginx está sirviendo su página default y **no** el contenido del inquilino. Sin una verificación del cuerpo de la respuesta, el health check no puede distinguir entre "sitio real con HTTP 200" y "nginx default con HTTP 200".

Adicionalmente: los incidentes creados por `router_health_guard` con `source_table='router_health_guard'` estaban siendo auto-resueltos por los jobs `sync_site_alerts` y `sync_system_alerts`, que los cerraban como "stale". Ver runbook `ROUTER_HEALTH_INCIDENTS_DELETED_BY_SYNC.md`.

## Diagnósticos equivocados
- **"El health check funciona porque detecta HTTP 200"** — HTTP 200 es condición necesaria pero no suficiente. El contenido de la respuesta debe ser verificado.
- **"Si Traefik enruta la petición y devuelve 200, el sitio está bien"** — Traefik sólo verifica la conectividad TCP con el contenedor destino. No inspecciona el contenido HTTP.
- **"El inquilino no se ha quejado, así que está bien"** — El cliente puede no haber accedido a su sitio recientemente, o puede estar esperando que el proveedor lo detecte. El monitoreo activo no puede depender de las quejas de los clientes.
- **"El dashboard tiene todos los checks en verde, es una prioridad baja"** — El estado verde del dashboard es precisamente el problema. El fallo está en la lógica del health check, no en los datos que reporta.

## Diagnóstico rápido
```bash
echo "=== Diagnóstico DASHBOARD_FALSE_100_HEALTH ==="

# Verificar todos los inquilinos activos buscando nginx default page
echo "[BODY CHECK] Escaneando inquilinos activos por nginx default page..."

# Obtener lista de inquilinos activos desde la API
TENANTS=$(curl -sf "http://localhost:8000/admin/tenants?status=active&limit=100" \
  -H "Authorization: Bearer $ADMIN_TOKEN" 2>/dev/null \
  | python3 -c "import sys,json; data=json.load(sys.stdin); [print(t.get('subdomain','')) for t in data.get('items',[])]" 2>/dev/null)

PROBLEMS=0
for TENANT in $TENANTS; do
  DOMAIN="${TENANT}.hostingguard.lat"
  BODY=$(curl -sf "https://$DOMAIN" 2>/dev/null || echo "")
  if echo "$BODY" | grep -qi "welcome to nginx"; then
    echo "  [FALSE POSITIVE] $DOMAIN — sirve nginx default page"
    PROBLEMS=$((PROBLEMS + 1))
  fi
done

echo "Total falsos positivos encontrados: $PROBLEMS"

# Verificar configuración del body check en router_health_guard
grep -n "welcome.*nginx\|body.*check\|check_body" /app/app/services/router_health_guard.py 2>/dev/null \
  || grep -rn "welcome.*nginx\|body.*check" /app/ 2>/dev/null | head -10
```

## Solución manual
Este incidente no tiene una "solución manual" en el sentido de un fix de emergencia — el dashboard mostrará el estado correcto una vez que el health check de cuerpo esté implementado. Las acciones inmediatas son:

```bash
# ACCIÓN INMEDIATA: Auditoría manual de todos los inquilinos
# Ejecutar el script de diagnóstico rápido (arriba) para identificar los afectados

# ACCIÓN INMEDIATA: Reparar los inquilinos con nginx default page
# Seguir el runbook WELCOME_TO_NGINX_EMPTY_SITE.md para cada inquilino afectado

# VERIFICAR si el body check está implementado en el código actual
grep -n "Welcome to nginx\|nginx.*default\|body_check" \
  /app/app/services/router_health_guard.py 2>/dev/null

# Si NO está implementado, el fix de código es urgente (ver Fix permanente abajo)

# VERIFICAR si los incidentes de router_health_guard están siendo auto-resueltos
# (ver runbook ROUTER_HEALTH_INCIDENTS_DELETED_BY_SYNC.md)
docker exec -i hg_db psql -U hguser -d hostingguard -c "
SELECT
  source_table,
  status,
  COUNT(*) as count,
  MAX(updated_at) as last_update
FROM system_incidents
WHERE source_table = 'router_health_guard'
GROUP BY source_table, status
ORDER BY last_update DESC;"
```

## Fix permanente
El health check de rutas debe verificar el cuerpo de la respuesta HTTP para detectar la página por defecto de nginx. En `router_health_guard.py`:

```python
NGINX_DEFAULT_MARKERS = [
    "Welcome to nginx!",
    "If you see this page, the nginx web server is successfully installed",
    "nginx/",  # en la página de error default de nginx
]

async def check_tenant_route_health(tenant: Tenant) -> RouteHealth:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"https://{tenant.subdomain}.hostingguard.lat",
                                timeout=10.0, follow_redirects=False)

    # Código de estado
    if resp.status_code == 404:
        return RouteHealth(status="unhealthy", reason="router_missing")

    if resp.status_code == 200:
        # Body check: verificar que no es la página por defecto de nginx
        body = resp.text
        for marker in NGINX_DEFAULT_MARKERS:
            if marker in body:
                return RouteHealth(
                    status="content_broken",
                    reason="nginx_default_page",
                    detail=f"HTTP 200 but serving nginx default page"
                )
        return RouteHealth(status="healthy")

    # Otros códigos (401, 302 para auth redirect) pueden ser válidos
    if resp.status_code in (401, 302):
        return RouteHealth(status="healthy", reason="auth_required")

    return RouteHealth(status="degraded", reason=f"unexpected_status_{resp.status_code}")
```

Adicionalmente, los jobs `sync_site_alerts` y `sync_system_alerts` deben filtrar por `source_type` y nunca auto-resolver incidentes con `source_table='router_health_guard'`.

## Señales para detección automática
- Body check en health monitor: respuesta HTTP 200 que contiene "Welcome to nginx!" para inquilino activo.
- Discrepancia: inquilino con `health_status='healthy'` en DB pero body check falla.
- Alert: `router_health_guard` crea incidente con `reason='nginx_default_page'` y severity `high`.
- El propio sistema de body check es la señal de detección una vez implementado.

## Auto-remediation permitido
Ninguna. El problema del dashboard es un problema de lógica de health check (código), no de infraestructura. No hay acción de auto-remediación que corrija el dashboard sin cambiar el código.

La reparación del inquilino subyacente (nginx sin mount) sí puede ser automática — ver `CONTAINER_WITH_EMPTY_MOUNTS.md`.

## Auto-remediation prohibido
- Marcar un inquilino como "healthy" basándose únicamente en HTTP 200 sin verificar el cuerpo. Esta es exactamente la causa del incidente.
- Auto-resolver incidentes creados por `router_health_guard` desde los jobs `sync_site_alerts` o `sync_system_alerts`.

## Dashboard esperado
Una vez que el body check esté implementado:
- Inquilinos sirviendo nginx default page aparecen con badge **HIGH**: "Content broken — nginx default page".
- Estado del inquilino: `content_broken` (no `healthy`).
- El resumen de salud global ya no muestra "100%" si hay inquilinos en estado `content_broken`.
- Panel "Router Health" distingue entre `healthy`, `content_broken`, `route_missing`, `degraded`.

## RAG usage
Este runbook se usa cuando el administrador pregunta "¿por qué el dashboard dice 100% healthy si el cliente reporta que su sitio está roto?". La IA debe explicar el falso positivo del HTTP 200, verificar si el body check está implementado en el código, y auditar manualmente los inquilinos activos para detectar cuántos sirven la nginx default page. La IA debe referenciar `WELCOME_TO_NGINX_EMPTY_SITE.md` para el fix de cada inquilino afectado y `ROUTER_HEALTH_INCIDENTS_DELETED_BY_SYNC.md` para el problema de auto-resolución de incidentes.

## Tests/Chaos
```bash
#!/bin/bash
# chaos/test_dashboard_false_100_health.sh
# Verifica que el body check detecta la nginx default page correctamente

set -euo pipefail

TENANT="${1:-mi-academia}"

echo "=== Test: body check de nginx default page ==="

# Crear una situación de nginx default (sin mount)
IMAGE=$(docker inspect "${TENANT}" --format='{{.Config.Image}}' 2>/dev/null || echo "nginx:alpine")
NETWORK=$(docker inspect "${TENANT}" --format='{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}' 2>/dev/null || echo "hg_network")

echo "[CHAOS] Recrear ${TENANT} sin mount (nginx default)"
docker stop "${TENANT}" 2>/dev/null && docker rm "${TENANT}" 2>/dev/null
docker run -d --name "${TENANT}" --network "${NETWORK}" --restart unless-stopped "${IMAGE}"
sleep 3

echo "[TEST] Verificar body check de la API de health"
HEALTH=$(curl -sf "http://localhost:8000/admin/router-health/tenants/${TENANT}/status" \
  -H "Authorization: Bearer $ADMIN_TOKEN" 2>/dev/null | python3 -m json.tool)
echo "  Health report: $HEALTH"

# Verificar que el status NO es 'healthy'
STATUS=$(echo "$HEALTH" | python3 -c "import sys,json; data=json.load(sys.stdin); print(data.get('status','unknown'))" 2>/dev/null)
if [ "$STATUS" = "healthy" ]; then
  echo "[FAIL] Falso positivo detectado — el body check no está funcionando"
else
  echo "[OK] Estado correcto: $STATUS (no es healthy)"
fi

echo "[RECOVER] Restaurar contenedor con mount"
docker stop "${TENANT}" 2>/dev/null && docker rm "${TENANT}" 2>/dev/null
docker run -d \
  --name "${TENANT}" \
  --network "${NETWORK}" \
  --restart unless-stopped \
  -v "/opt/clients/${TENANT}:/usr/share/nginx/html:ro" \
  "${IMAGE}"
sleep 3
echo "[DONE] Contenedor restaurado"
```
