---
incident_id: ROUTER_HEALTH_INCIDENTS_DELETED_BY_SYNC
incident_type: observability
severity: high
status: confirmed
validated: true
auto_repair_allowed: false
safe_actions:
  - add_source_type_filter_to_sync_handlers
forbidden_actions:
  - delete_all_open_incidents
  - auto_resolve_incidents_without_source_check
signatures:
  - "router_health_guard incident closed by sync job"
  - "source_table=router_health_guard AND status changed to resolved by sync"
  - "incident auto-closed without human review"
  - "sync_site_alerts resolved router_health incident"
---

# ROUTER_HEALTH_INCIDENTS_DELETED_BY_SYNC

## Síntoma
Los incidentes de salud de rutas creados por `router_health_guard.py` aparecen como resueltos/cerrados en la base de datos poco tiempo después de ser creados, aunque el problema real no haya sido corregido. El panel de incidentes activos parece "limpio" pero los inquilinos siguen con problemas. El sistema crea el incidente, el job de sincronización lo cierra, el system crea el incidente de nuevo, y así sucesivamente — el administrador ve incidentes que aparecen y desaparecen.

## Impacto
- Los incidentes de salud de rutas no persisten en el panel de administración.
- No se genera alerta sostenida para el administrador (el incidente se cierra antes de que el canal de notificación lo procese).
- La historia de incidentes es inutilizable para análisis post-mortem.
- El problema subyacente (contenedor sin mount, ruta 404, etc.) nunca se resuelve porque nadie lo ve.
- Rompe el invariante del sistema: los incidentes deben persistir hasta que sean revisados por un humano o resueltos por auto-remediación validada.

## Evidencia
```bash
# Ver el historial de cambios de estado de incidentes de router_health_guard
docker exec -i hg_db psql -U hguser -d hostingguard -c "
SELECT
  id,
  tenant_id,
  incident_type,
  source_table,
  status,
  created_at,
  updated_at,
  resolved_at,
  resolved_by
FROM system_incidents
WHERE source_table = 'router_health_guard'
ORDER BY created_at DESC
LIMIT 20;"

# Detectar el patrón: incidentes creados y cerrados rápidamente
docker exec -i hg_db psql -U hguser -d hostingguard -c "
SELECT
  id,
  source_table,
  status,
  created_at,
  updated_at,
  EXTRACT(EPOCH FROM (updated_at - created_at)) as seconds_to_close,
  resolved_by
FROM system_incidents
WHERE source_table = 'router_health_guard'
  AND status IN ('resolved', 'closed')
  AND EXTRACT(EPOCH FROM (updated_at - created_at)) < 300
ORDER BY created_at DESC
LIMIT 20;"

# Ver los logs del job sync_site_alerts buscando referencias a router_health
docker compose -f /opt/deploy/docker-compose.yml logs --tail=200 scheduler 2>&1 \
  | grep -i "sync.*alert\|resolve\|router_health\|source_type"

# Ver qué fuente resolvió los incidentes
docker exec -i hg_db psql -U hguser -d hostingguard -c "
SELECT DISTINCT resolved_by, COUNT(*) as total
FROM system_incidents
WHERE source_table = 'router_health_guard'
  AND resolved_by IS NOT NULL
GROUP BY resolved_by;"
```

## Causa raíz
Los jobs periódicos `sync_site_alerts` y `sync_system_alerts` implementan una lógica de "stale cleanup": cierran todos los incidentes abiertos cuya fuente ya no reporta un problema activo. El problema es que estos jobs **no filtraban por `source_type`** — trataban todos los incidentes abiertos indiscriminadamente. Los incidentes de `router_health_guard` tienen `source_table='router_health_guard'` y `source_type='router_health'`, pero los jobs de sincronización de alertas de sitio no reconocían este origen y los cerraban al no encontrar una alerta activa correspondiente en las fuentes que ellos monitoreaban (monitoreo de sitios, no de salud de rutas).

El `source_type` es el campo que actúa como firewall: los jobs de sincronización sólo deben procesar incidentes de su propio `source_type`.

## Diagnósticos equivocados
- **"Los incidentes se resolvieron solos porque el problema se arregló"** — Si el problema se hubiera arreglado, el campo `resolved_by` tendría el nombre del proceso correcto y el contenedor tendría el mount correcto. Verificar el estado actual del contenedor.
- **"Hay un bug en router_health_guard que crea y cierra sus propios incidentes"** — `router_health_guard` crea incidentes pero no tiene código para cerrarlos. Si se están cerrando, es otro proceso.
- **"El administrador cerró los incidentes manualmente"** — Si `resolved_by` muestra el nombre de un job automático (ej. `sync_site_alerts`), no fue acción humana.
- **"Es un problema de duplicación de incidentes"** — El ciclo crear/cerrar/crear es síntoma de que el sync job cierra lo que el health guard crea, no que haya duplicados.

## Diagnóstico rápido
```bash
echo "=== Diagnóstico ROUTER_HEALTH_INCIDENTS_DELETED_BY_SYNC ==="

# 1. Buscar incidentes de router_health_guard cerrados en menos de 5 minutos
echo "[PATTERN] Incidentes de router_health_guard cerrados rápidamente:"
docker exec -i hg_db psql -U hguser -d hostingguard -t -c "
SELECT COUNT(*)
FROM system_incidents
WHERE source_table = 'router_health_guard'
  AND status IN ('resolved', 'closed')
  AND EXTRACT(EPOCH FROM (COALESCE(resolved_at, updated_at) - created_at)) < 300;"

# 2. Ver quién resolvió los últimos incidentes de router_health_guard
echo "[RESOLVED_BY] Últimos resolutores de incidentes router_health_guard:"
docker exec -i hg_db psql -U hguser -d hostingguard -c "
SELECT resolved_by, COUNT(*) FROM system_incidents
WHERE source_table = 'router_health_guard' AND resolved_by IS NOT NULL
GROUP BY resolved_by ORDER BY COUNT(*) DESC;"

# 3. Ver el código de los sync handlers para confirmar el bug
grep -n "source_type\|source_table\|router_health\|sync.*alert" \
  /app/app/services/sync_site_alerts.py \
  /app/app/services/sync_system_alerts.py 2>/dev/null | head -30

# 4. Ver si el scheduler está configurado para ejecutar sync en un intervalo corto
grep -n "sync.*alert\|cron\|interval" /app/app/services/scheduler_runner.py 2>/dev/null | head -20
```

## Solución manual
```bash
# PASO 1: Identificar y reabrir los incidentes cerrados incorrectamente
docker exec -i hg_db psql -U hguser -d hostingguard -c "
UPDATE system_incidents
SET
  status = 'open',
  resolved_at = NULL,
  resolved_by = NULL,
  updated_at = NOW()
WHERE source_table = 'router_health_guard'
  AND status IN ('resolved', 'closed')
  AND EXTRACT(EPOCH FROM (COALESCE(resolved_at, updated_at) - created_at)) < 300
  AND resolved_by IN ('sync_site_alerts', 'sync_system_alerts', 'stale_cleanup')
RETURNING id, tenant_id, status, updated_at;"

echo "Incidentes reabiertos."

# PASO 2: Editar el código de sync_site_alerts para agregar el filtro de source_type
# En /app/app/services/sync_site_alerts.py, agregar filtro:
# WHERE source_type NOT IN ('router_health') AND source_table != 'router_health_guard'
# Ver Fix permanente para el código exacto.

# PASO 3: Editar el código de sync_system_alerts de forma similar

# PASO 4: Desplegar el fix (rebuild del contenedor scheduler/worker)
docker compose -f /opt/deploy/docker-compose.yml up -d --build scheduler

# PASO 5: Verificar que los incidentes de router_health_guard ya no se cierran automáticamente
# Esperar 2 ciclos del scheduler y verificar:
sleep 120  # esperar 2 minutos
docker exec -i hg_db psql -U hguser -d hostingguard -c "
SELECT id, status, updated_at, resolved_by
FROM system_incidents
WHERE source_table = 'router_health_guard'
  AND status = 'open'
ORDER BY updated_at DESC LIMIT 10;"
# Los incidentes open deben permanecer open
```

## Fix permanente
En cada job de sincronización de alertas, agregar un filtro explícito por `source_type` antes de cualquier operación de resolución:

**`sync_site_alerts.py`:**
```python
# ANTES (buggy):
stale_incidents = db.query(SystemIncident).filter(
    SystemIncident.status == 'open',
    SystemIncident.created_at < cutoff_time
).all()

# DESPUÉS (correcto):
EXCLUDED_SOURCE_TYPES = {'router_health', 'manual', 'admin'}
EXCLUDED_SOURCE_TABLES = {'router_health_guard'}

stale_incidents = db.query(SystemIncident).filter(
    SystemIncident.status == 'open',
    SystemIncident.created_at < cutoff_time,
    SystemIncident.source_type.notin_(EXCLUDED_SOURCE_TYPES),
    SystemIncident.source_table.notin_(EXCLUDED_SOURCE_TABLES)
).all()
```

La regla general: un job de sincronización sólo debe cerrar incidentes cuyo `source_type` coincide con el suyo propio. Los incidentes de `router_health_guard` sólo deben ser cerrados por `router_health_guard` o por acción humana explícita.

## Señales para detección automática
- Patrón de "flip": incidente `router_health_guard` abierto y cerrado en menos de 5 minutos más de 3 veces para el mismo `tenant_id`.
- `resolved_by = 'sync_site_alerts'` o `'sync_system_alerts'` en incidentes con `source_table = 'router_health_guard'`.
- Alerta meta: el sistema de monitoreo debe alertar si detecta que sus propios incidentes están siendo cerrados por procesos no autorizados.

## Auto-remediation permitido
Agregar el filtro de `source_type` al código de los jobs de sincronización (acción: `add_source_type_filter_to_sync_handlers`). Este cambio es un fix de código, no una acción de infraestructura. Requiere build y despliegue del contenedor.

## Auto-remediation prohibido
- Cerrar todos los incidentes abiertos como medida de "limpieza". Esto enmascara problemas reales.
- Auto-resolver incidentes sin verificar si el problema subyacente sigue activo y sin respetar el campo `source_type`.

## Dashboard esperado
Una vez corregido el fix:
- Los incidentes de `router_health_guard` persisten en el panel de "Incidentes Activos" hasta ser revisados.
- El campo "Fuente" en el panel de incidentes muestra `router_health_guard` y no puede ser cerrado por jobs automáticos de sincronización.
- Badge de auditoría: "X incidentes de salud de rutas requieren revisión humana".

## RAG usage
Cuando el administrador reporte "los incidentes desaparecen solos" o "el sistema detecta problemas pero los cierra inmediatamente", la IA debe verificar el campo `resolved_by` de los incidentes recientes de `router_health_guard`. Si el resolutor es un job de sincronización, este runbook es el correcto. La IA debe explicar el problema del filtrado por `source_type` y el código de fix. Este runbook es complementario a `DASHBOARD_FALSE_100_HEALTH.md` — ambos son problemas de observabilidad que se retroalimentan.

## Tests/Chaos
```bash
#!/bin/bash
# chaos/test_router_health_incidents_not_deleted.sh
# Verifica que sync_site_alerts NO cierra incidentes de router_health_guard

set -euo pipefail

echo "=== Test: router_health incidents no son cerrados por sync jobs ==="

# Crear un incidente de prueba con source_table=router_health_guard
INCIDENT_ID=$(docker exec -i hg_db psql -U hguser -d hostingguard -t -c "
INSERT INTO system_incidents
  (tenant_id, incident_type, severity, status, source_table, source_type, description, created_at, updated_at)
VALUES
  (NULL, 'route_health', 'high', 'open', 'router_health_guard', 'router_health',
   'Test incident — chaos test', NOW(), NOW())
RETURNING id;" | tr -d ' \n')

echo "[CHAOS] Incidente de prueba creado: ID=$INCIDENT_ID"

# Esperar un ciclo del scheduler (ajustar según intervalo configurado)
echo "[WAIT] Esperando 2 ciclos del scheduler..."
sleep 120

# Verificar que el incidente sigue abierto
STATUS=$(docker exec -i hg_db psql -U hguser -d hostingguard -t -c "
SELECT status FROM system_incidents WHERE id = $INCIDENT_ID;" | tr -d ' \n')

echo "[CHECK] Estado del incidente $INCIDENT_ID: $STATUS"

if [ "$STATUS" = "open" ]; then
  echo "[OK] El incidente de router_health_guard NO fue cerrado por el sync job"
else
  echo "[FAIL] El incidente fue cerrado automáticamente — el filtro source_type no está implementado"
  docker exec -i hg_db psql -U hguser -d hostingguard -c \
    "SELECT id, status, resolved_by, updated_at FROM system_incidents WHERE id = $INCIDENT_ID;"
fi

# Limpiar el incidente de prueba
docker exec -i hg_db psql -U hguser -d hostingguard -c \
  "DELETE FROM system_incidents WHERE id = $INCIDENT_ID AND description LIKE '%chaos test%';"
echo "[CLEANUP] Incidente de prueba eliminado"
```
