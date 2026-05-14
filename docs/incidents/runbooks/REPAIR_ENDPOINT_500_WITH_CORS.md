---
incident_id: REPAIR_ENDPOINT_500_WITH_CORS
incident_type: api
severity: medium
status: confirmed
validated: true
auto_repair_allowed: false
safe_actions: []
forbidden_actions:
  - disable_cors_check
  - return_raw_exceptions_to_client
signatures:
  - "POST /admin/router-health/tenants/{id}/repair 500"
  - "CORS error on 500 response"
  - "No 'Access-Control-Allow-Origin' header on error response"
  - "Cross-Origin Request Blocked"
  - "Internal Server Error without CORS headers"
---

# REPAIR_ENDPOINT_500_WITH_CORS

## Síntoma
Al hacer clic en "Reparar" en el panel de salud de rutas del dashboard de administración, el navegador muestra un error de CORS en la consola del desarrollador: `"Cross-Origin Request Blocked: The Same Origin Policy disallows reading the remote resource"`. La petición `POST /admin/router-health/tenants/{id}/repair` devuelve 500 con un cuerpo que no es JSON (o sin cuerpo), y el middleware CORS de FastAPI no incluye los headers `Access-Control-Allow-Origin` en la respuesta de error.

## Impacto
- El botón "Reparar" del dashboard no funciona — la acción de reparación no se ejecuta.
- El administrador no puede auto-reparar inquilinos desde la interfaz web.
- La consola del navegador muestra el error CORS, que es un síntoma secundario; el error real es el 500 en el servidor.
- Las llamadas directas a la API (ej. via curl) sí muestran el error real del servidor.

## Evidencia
```bash
# Confirmar el error 500 sin CORS (llamada directa, sin browser)
curl -sv -X POST "http://localhost:8000/admin/router-health/tenants/TENANT_ID/repair" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" 2>&1 | grep -E "< HTTP|< Access-Control|{|}"

# Ver el error real en los logs del servidor (el traceback que el 500 oculta)
docker compose -f /opt/deploy/docker-compose.yml logs --tail=50 app 2>&1 \
  | grep -A 20 "ERROR\|500\|repair\|Traceback"

# Verificar si el endpoint existe y tiene manejo de errores
grep -n "repair\|try.*except\|HTTPException" \
  /app/app/api/admin/router_health.py 2>/dev/null | head -20

# Verificar configuración CORS en la app
grep -n "CORSMiddleware\|allow_origins\|allow_methods" \
  /app/app/main.py 2>/dev/null

# Reproducir el error con el header Origin para confirmar el problema CORS
curl -sv -X POST "http://localhost:8000/admin/router-health/tenants/TENANT_ID/repair" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Origin: https://hostingguard.lat" \
  -H "Content-Type: application/json" 2>&1 | grep -E "< HTTP|< Access-Control|{|Error}"
```
Salida esperada del problema:
```
< HTTP/1.1 500 Internal Server Error
< content-type: text/plain
# AUSENTE: Access-Control-Allow-Origin: https://hostingguard.lat
```

## Causa raíz
El endpoint `POST /admin/router-health/tenants/{id}/repair` lanzaba una excepción no capturada (ej. `FileNotFoundError` al intentar leer el YAML del inquilino, o `subprocess.CalledProcessError` al ejecutar `docker run`). FastAPI convierte las excepciones no capturadas en respuestas 500 con `content-type: text/plain` o `content-type: application/json` con el traceback (si `debug=True`). El problema con CORS es que el middleware `CORSMiddleware` de FastAPI/Starlette añade los headers `Access-Control-Allow-Origin` **en el middleware layer**, pero si la excepción se propaga antes de que el middleware la procese correctamente (o si la respuesta 500 se genera fuera del pipeline normal), los headers CORS pueden no incluirse en la respuesta de error.

La solución es doble:
1. Capturar la excepción en el endpoint con `try/except` y devolver un `HTTPException` controlado.
2. Asegurarse de que `CORSMiddleware` está registrado de forma que cubra **todas** las respuestas, incluyendo las de error.

## Diagnósticos equivocados
- **"El problema es CORS — hay que cambiar la configuración CORS"** — CORS es el síntoma visible en el browser, no la causa. La causa es el 500. Si el endpoint devolviera una respuesta JSON correcta (aunque fuera un error), CORS funcionaría bien.
- **"El browser bloquea la petición por seguridad"** — El browser bloquea la respuesta al leerla, pero la petición sí llega al servidor. El 500 ocurre en el servidor.
- **"Hay que agregar el origin del admin a la allowlist de CORS"** — Si CORS funciona para otros endpoints pero falla en éste, el problema es específico de la respuesta 500, no de la configuración CORS global.
- **"Es un problema del preflight OPTIONS"** — El preflight OPTIONS sería un problema diferente (el browser no enviaría POST). Si el POST llega y devuelve 500, el preflight funcionó correctamente.

## Diagnóstico rápido
```bash
echo "=== Diagnóstico REPAIR_ENDPOINT_500_WITH_CORS ==="

# 1. Probar el endpoint directamente (sin browser, sin CORS)
TENANT_ID="${1:-1}"  # ajustar al ID del inquilino
echo "[DIRECT] Prueba directa del endpoint (sin Origin header):"
curl -s -X POST "http://localhost:8000/admin/router-health/tenants/${TENANT_ID}/repair" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -w "\nHTTP: %{http_code}" | tail -5

# 2. Ver el traceback en logs
echo "[LOGS] Últimos errores del endpoint de repair:"
docker compose -f /opt/deploy/docker-compose.yml logs --since=10m app 2>&1 \
  | grep -B 2 -A 10 "repair\|500\|Traceback\|Exception"

# 3. Verificar que CORSMiddleware está configurado para incluir error responses
echo "[CORS] Configuración CORS en main.py:"
grep -A 10 "CORSMiddleware" /app/app/main.py 2>/dev/null

# 4. Probar con Origin header (simular browser)
echo "[CORS TEST] Prueba con Origin header:"
curl -s -X POST "http://localhost:8000/admin/router-health/tenants/${TENANT_ID}/repair" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Origin: https://hostingguard.lat" \
  -D - 2>/dev/null | grep -E "HTTP|Access-Control|content-type"
```

## Solución manual
```bash
# El fix es un cambio de código — no hay solución manual de infraestructura.
# Workaround inmediato: ejecutar la reparación directamente via curl en el servidor
# (evita el browser y el CORS)

TENANT_ID="AJUSTAR"  # ID del inquilino en la DB

echo "[WORKAROUND] Ejecutar reparación directamente en el servidor:"
curl -X POST "http://localhost:8000/admin/router-health/tenants/${TENANT_ID}/repair" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  | python3 -m json.tool

# Si el endpoint falla con 500, ver el error real en los logs:
docker compose -f /opt/deploy/docker-compose.yml logs --tail=20 app 2>&1 | grep -A 15 "ERROR\|500"

# El fix de código (ver Fix permanente) debe desplegarse para que el botón
# del dashboard funcione correctamente.
```

## Fix permanente
Dos cambios necesarios:

**1. Capturar excepciones en el endpoint de repair:**
```python
# En app/api/admin/router_health.py

@router.post("/tenants/{tenant_id}/repair")
async def repair_tenant_route(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> RepairResponse:
    try:
        tenant = await get_tenant_or_404(db, tenant_id)
        result = await repair_tenant_traefik_route(tenant)
        return RepairResponse(success=True, detail=result)
    except TenantNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(
            status_code=503,
            detail={"code": "repair_permission_denied", "error": str(e)}
        )
    except Exception as e:
        logger.exception(f"Unexpected error repairing tenant {tenant_id}")
        raise HTTPException(
            status_code=500,
            detail={"code": "repair_failed", "error": "Internal repair error"}
        )
```

**2. Asegurar que CORSMiddleware cubre respuestas de error:**
```python
# En app/main.py — el CORSMiddleware debe estar registrado ANTES de cualquier otro middleware
# y el parámetro expose_headers debe estar configurado correctamente

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# NOTA: En Starlette/FastAPI, CORSMiddleware envuelve todas las respuestas
# incluyendo 500. Si el 500 viene de una excepción no capturada (antes del
# middleware), los headers CORS no se añaden. Por eso el try/except en el
# endpoint es la solución más robusta.
```

## Señales para detección automática
- HTTP 500 en el endpoint `POST /admin/router-health/tenants/*/repair` en los logs de acceso de Traefik/app.
- Log pattern: `"Exception"` o `"Traceback"` en logs del contenedor `app` asociado a requests de repair.
- Monitoreo de endpoints críticos: test automático que ejecuta el endpoint de repair en un inquilino de prueba y verifica que devuelve JSON válido con código 200 o 4xx (nunca 500 no controlado).

## Auto-remediation permitido
Ninguna. Este es un bug de código que requiere fix y despliegue. No hay acción de infraestructura que lo solucione.

## Auto-remediation prohibido
- Deshabilitar CORS para el endpoint de repair como workaround. El CORS existe por razones de seguridad.
- Devolver excepciones raw (traceback completo) al cliente. Expone información interna del servidor.
- Silenciar el error 500 devolviendo 200 sin ejecutar la acción de reparación.

## Dashboard esperado
Una vez corregido:
- El botón "Reparar" del panel de salud de rutas devuelve una respuesta JSON con el resultado de la reparación (éxito o error descriptivo).
- Si la reparación falla, el dashboard muestra el mensaje de error específico (ej. "archivo de cliente no encontrado"), no un error de red genérico.
- Los errores 4xx/5xx del endpoint de repair se registran en `system_incidents` con `incident_type='api_error'`.

## RAG usage
Cuando el administrador reporte "el botón de reparar no funciona" o "error CORS al reparar", la IA debe distinguir entre el síntoma CORS (visible en el browser) y la causa real (500 en el servidor). El primer paso es reproducir el error con `curl` directamente en el servidor para ver el error real sin interferencia CORS. Luego verificar los logs de la app para el traceback. El fix es código Python en el endpoint de repair — la IA debe sugerir el patrón `try/except` → `HTTPException` descrito en "Fix permanente".

## Tests/Chaos
```bash
#!/bin/bash
# chaos/test_repair_endpoint_error_handling.sh
# Verifica que el endpoint de repair devuelve JSON correcto en casos de error

set -euo pipefail

echo "=== Test: repair endpoint error handling ==="

# Test 1: Inquilino inexistente (debe devolver 404 JSON, no 500)
echo "[TEST 1] Inquilino inexistente:"
RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST "http://localhost:8000/admin/router-health/tenants/999999/repair" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json")
HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -1)
echo "  HTTP: $HTTP_CODE (esperado: 404)"
echo "  Body: $BODY"
if [ "$HTTP_CODE" = "404" ]; then echo "[OK]"; else echo "[FAIL] Esperado 404, obtenido $HTTP_CODE"; fi

# Test 2: Con Origin header — verificar que la respuesta incluye CORS headers
echo "[TEST 2] Verificar CORS headers en respuesta de error:"
HEADERS=$(curl -sI -X POST \
  "http://localhost:8000/admin/router-health/tenants/999999/repair" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Origin: https://hostingguard.lat" \
  -H "Content-Type: application/json")
echo "$HEADERS" | grep -i "access-control-allow-origin" \
  && echo "[OK] CORS header presente" \
  || echo "[FAIL] CORS header ausente en respuesta de error"

# Test 3: Verificar que ninguna respuesta devuelve 500 sin JSON body
echo "[TEST 3] Verificar que 500 incluye JSON body (si ocurre):"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "http://localhost:8000/admin/router-health/tenants/999999/repair" \
  -H "Authorization: Bearer $ADMIN_TOKEN")
if [ "$HTTP_CODE" = "500" ]; then
  echo "[FAIL] El endpoint devuelve 500 — revisar manejo de excepciones"
else
  echo "[OK] No se obtuvo 500 inesperado (HTTP: $HTTP_CODE)"
fi
```
