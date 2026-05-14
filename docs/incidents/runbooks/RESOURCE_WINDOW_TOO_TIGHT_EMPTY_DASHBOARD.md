---
incident_id: RESOURCE_WINDOW_TOO_TIGHT_EMPTY_DASHBOARD
incident_type: ui_data_gap
severity: low
status: confirmed
validated: true
auto_repair_allowed: false
safe_actions: []
forbidden_actions:
  - backfill_fake_metrics
  - disable_resource_dashboard
signatures:
  - "no data.*dashboard"
  - "empty chart"
  - "no metrics found"
---

# RESOURCE_WINDOW_TOO_TIGHT_EMPTY_DASHBOARD

## Síntoma
El dashboard de recursos de un hosting muestra gráficas vacías o "No hay datos disponibles" para todas las métricas (CPU, RAM, disco, red). El sistema de recolección de métricas está funcionando correctamente. El problema es que la ventana de tiempo de la consulta es demasiado estrecha y no incluye ningún punto de datos.

## Impacto
- El cliente o el administrador no puede ver el historial de recursos del hosting.
- Puede generar tickets de soporte ("el dashboard no funciona").
- No hay impacto en el funcionamiento del hosting ni en la recolección de datos.
- Los datos sí existen en la base de datos; simplemente no se están mostrando.

## Evidencia
```json
// API response de /hostings/{id}/metrics?window=5m
{
  "data": [],
  "message": "no metrics found for the requested time window",
  "window": "5m",
  "points": 0
}
```

```bash
# Verificar que sí hay datos en la BD para ese hosting
docker compose exec app python -c "
from app.db.session import get_db
from sqlalchemy import text
from datetime import datetime, timedelta
db = next(get_db())

# ¿Cuántos puntos hay en las últimas 2 horas?
result = db.execute(text(\"\"\"
  SELECT COUNT(*), MIN(recorded_at), MAX(recorded_at)
  FROM resource_metrics
  WHERE hosting_id = X
    AND recorded_at > NOW() - INTERVAL '2 hours'
\"\"\"))
print(list(result))
"
```

## Causa raíz
El colector de recursos ejecuta su ciclo cada **5 minutos**. Si la ventana de tiempo de la query del dashboard es de 5 minutos o menos, puede que solo haya 0 o 1 puntos en el rango:

- Si el último punto se registró hace 4:30 min y la ventana es de 5 min, puede haber 0 puntos en el rango exacto de la query dependiendo de cómo se calcula el `now()`.
- Ventanas estrechas con intervalos de agrupación pequeños (e.g., `GROUP BY 1 minute` en una ventana de 5 min) generan series casi vacías.
- El frontend puede interpretar un array vacío o con 1 punto como "sin datos" y no renderizar la gráfica.
- Hosting recién creado: no tiene métricas hasta que el primer ciclo del colector lo procesa.

## Diagnósticos equivocados
- **"El colector de métricas está caído"**: Verificar logs del scheduler. Si el colector funciona, el problema es la ventana de tiempo, no la recolección.
- **"No hay métricas para este hosting"**: Puede haber métricas fuera de la ventana consultada. Ampliar la ventana y verificar.
- **"El hosting no está activo"**: Un hosting activo pero recién creado puede no tener métricas todavía (esperar un ciclo).
- **"Error en la BD"**: Si la query retorna array vacío sin error, la BD está bien; simplemente no hay datos en esa ventana.

## Diagnóstico rápido
```bash
# 1. Verificar que el colector está funcionando
docker compose logs hg_scheduler --tail=50 | grep "collect_resource_usage\|metrics"

# 2. Verificar cuándo se registró el último punto de métricas para el hosting
docker compose exec app python -c "
from app.db.session import get_db
from sqlalchemy import text
db = next(get_db())
result = db.execute(text(\"\"\"
  SELECT recorded_at, cpu_usage_percent, memory_usage_mb
  FROM resource_metrics
  WHERE hosting_id = X
  ORDER BY recorded_at DESC LIMIT 3
\"\"\"))
for row in result: print(row)
"

# 3. Probar la API con una ventana más amplia
curl -s "https://api.hostingguard.example/hostings/X/metrics?window=2h" \
  -H "Cookie: access_token=<token>" | python -m json.tool | head -30

# 4. Verificar la ventana por defecto que está usando el frontend
# Inspeccionar la llamada de red en DevTools del navegador
```

## Solución manual
### Para el cliente (acción inmediata):
Indicar al cliente que amplíe la ventana de tiempo en el selector del dashboard:
- Cambiar de "Últimos 5 min" → "Última hora" o "Últimas 24h"

### Si el hosting es nuevo (sin datos todavía):
```bash
# Verificar cuándo fue creado el hosting
docker compose exec app python -c "
from app.db.session import get_db
from sqlalchemy import text
db = next(get_db())
result = db.execute(text(\"SELECT created_at, status FROM hostings WHERE id=X\"))
print(list(result))
"
# Si fue creado hace menos de 5 min, esperar el primer ciclo del colector
```

### Para el administrador:
No hay acción de corrección de datos necesaria. El fix es en la UI o en la configuración de la ventana por defecto.

## Fix permanente
1. **Cambiar la ventana por defecto** en el dashboard de recursos:
   - Reemplazar el default de `5m` por `1h` o `6h`.
   - Añadir un selector de ventana de tiempo con opciones: 1h, 6h, 24h, 7d.

2. **Manejo de respuesta vacía en el frontend**:
   ```typescript
   // En el componente de gráfica de recursos
   if (metrics.length === 0) {
     return (
       <EmptyState
         title="Sin datos disponibles"
         description={`No hay métricas en los últimos ${window}. 
                       El colector ejecuta cada 5 minutos. 
                       Prueba ampliar la ventana de tiempo.`}
         action={<Button onClick={() => setWindow('1h')}>Ver última hora</Button>}
       />
     );
   }
   ```

3. **Para hostings nuevos**: mostrar un banner "Las métricas estarán disponibles en los próximos 5 minutos" si el hosting fue creado hace menos de 10 minutos y no tiene datos.

4. **En la API**: si la ventana es menor que 2 veces el intervalo del colector (< 10 min), retornar un warning en la respuesta:
   ```json
   {
     "data": [],
     "warning": "Window is smaller than 2x collection interval (5min). Expand to at least 10 minutes for reliable results."
   }
   ```

## Señales para detección automática
- Query a `/metrics` con ventana < 10 min retorna `data: []`
- Tasa de respuestas vacías en `/metrics` > 30% para la ventana de 5 min
- Ticket de soporte: "dashboard vacío" o "no veo datos de recursos"

## Auto-remediation permitido
Ninguna. El fix es de UI/configuración, no de datos.

## Auto-remediation prohibido
- `backfill_fake_metrics`: Nunca insertar datos de métricas ficticios para "rellenar" gráficas vacías. Corrompe el historial real y puede triggear alertas falsas.
- `disable_resource_dashboard`: Deshabilitar el dashboard como solución es peor que el problema original.

## Dashboard esperado
- **Ventana por defecto**: 1 hora o mayor.
- **Mensaje informativo**: si la ventana está vacía, mostrar explicación y botón para ampliar.
- **Métricas disponibles**: dentro de 5-10 minutos tras crear un hosting.
- **Tasa de dashboards vacíos**: < 5% con la ventana correcta.

## RAG usage
Recuperar con: `empty dashboard resource metrics time window`, `no metrics found window too tight`, `dashboard no data 5 minutes`.
Contexto relevante: endpoint `/hostings/{id}/metrics`, componentes React de gráficas de recursos, configuración del colector (intervalo 5 min).

## Tests/Chaos
```python
# Test: ventana de 5 min en un hosting con datos puede retornar vacío → API debe dar warning
def test_narrow_window_returns_warning(client, auth_headers, hosting_with_metrics):
    response = client.get(
        f"/hostings/{hosting_with_metrics.id}/metrics?window=5m",
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    # Si está vacío, debe incluir warning
    if len(data["data"]) == 0:
        assert "warning" in data

# Test: ventana de 1h con datos del colector retorna puntos
def test_1h_window_returns_data(client, auth_headers, hosting_with_metrics):
    response = client.get(
        f"/hostings/{hosting_with_metrics.id}/metrics?window=1h",
        headers=auth_headers
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) > 0
```
