---
incident_id: RESOURCES_MISSING_CONTAINER_BREAKS_COLLECTOR
incident_type: collector_crash
severity: medium
status: confirmed
validated: true
auto_repair_allowed: true
safe_actions:
  - skip_missing_container_in_metrics
forbidden_actions:
  - delete_hosting_record_when_container_missing
  - stop_all_metric_collection
signatures:
  - "No such container: user_"
  - "Error: No such container"
---

# RESOURCES_MISSING_CONTAINER_BREAKS_COLLECTOR

## Síntoma
El colector de recursos (`collect_resource_usage.py`) lanza una excepción no capturada al intentar inspeccionar un contenedor que está en la base de datos pero ya no existe en Docker. El error `No such container: user_X_Y` hace que el ciclo de recolección completo falle, dejando sin métricas a TODOS los hostings durante ese intervalo, no solo al afectado.

## Impacto
- **Crítico en cascada**: Un solo contenedor fantasma rompe la recolección de métricas para todos los clientes en ese poll cycle.
- El dashboard de recursos muestra datos desactualizados o vacíos para todos los hostings.
- Las alertas basadas en métricas de recursos no se disparan durante la outage del colector.
- El contenedor en cuestión probablemente fue eliminado manualmente, terminó de forma anormal, o hay una inconsistencia de estado en la BD.
- No hay pérdida de datos históricos; solo se pierden los puntos del ciclo fallido.

## Evidencia
```
docker.errors.NotFound: 404 Client Error for http+docker://localhost/v1.X/containers/user_42_wordpress/stats:
Not Found ("No such container: user_42_wordpress")

# En scheduler logs:
ERROR: collect_resource_usage failed for user_42_wordpress: No such container: user_42_wordpress
# Y a continuación, ninguna métrica para otros hostings en ese ciclo
```

```bash
docker compose logs hg_scheduler | grep "No such container"
docker compose logs hg_scheduler | grep "collect_resource_usage"
```

## Causa raíz
El colector itera sobre todos los hostings activos en la BD y llama al Docker daemon para obtener estadísticas de cada contenedor. La excepción `docker.errors.NotFound` no está capturada dentro del loop de iteración, sino que se propaga hacia arriba y cancela el ciclo completo.

Escenarios que generan contenedores fantasma:
1. El contenedor fue eliminado manualmente con `docker rm` sin actualizar la BD.
2. Docker pruned los contenedores detenidos (`docker system prune`).
3. Una terminación fallida dejó el registro en BD como "activo" pero sin contenedor real.
4. Migración o renombrado del contenedor sin actualizar `container_name` en la BD.

## Diagnósticos equivocados
- **"El Docker daemon está caído"**: Si solo falla un contenedor con `NotFound`, el daemon está operativo.
- **"Problema de red con el Docker socket"**: El error específico es `NotFound` (404), no un error de conexión.
- **"La BD está corrupta"**: La BD es consistente; es Docker quien no tiene el contenedor.

## Diagnóstico rápido
```bash
# 1. Identificar el contenedor fantasma
docker compose logs hg_scheduler --tail=200 | grep "No such container"

# 2. Listar contenedores activos en Docker vs activos en BD
docker ps --format "{{.Names}}" | sort > /tmp/docker_containers.txt

docker compose exec app python -c "
from app.db.session import get_db
from sqlalchemy import text
db = next(get_db())
result = db.execute(text(\"SELECT container_name FROM hostings WHERE status='active'\"))
for row in result: print(row[0])
" | sort > /tmp/db_containers.txt

diff /tmp/docker_containers.txt /tmp/db_containers.txt
# Las líneas solo en db_containers.txt son los contenedores fantasma

# 3. Verificar el estado del hosting en BD
docker compose exec app python -c "
from app.db.session import get_db
from sqlalchemy import text
db = next(get_db())
result = db.execute(text(\"SELECT id, container_name, status FROM hostings WHERE container_name='user_X_Y'\"))
for row in result: print(row)
"
```

## Solución manual
### Inmediata: Actualizar el estado del hosting fantasma en BD
```bash
# Si el contenedor fue terminado intencionalmente:
docker compose exec app python -c "
from app.db.session import get_db
from sqlalchemy import text
db = next(get_db())
db.execute(text(\"UPDATE hostings SET status='terminated' WHERE container_name='user_X_Y'\"))
db.commit()
print('Done')
"

# Verificar que el colector se recupera en el próximo ciclo
docker compose logs -f hg_scheduler | grep "collect_resource_usage"
```

### Si el contenedor debe existir (terminación anormal):
```bash
# Verificar si hay imagen disponible para recrearlo
docker images | grep user_X_Y

# Revisar en /opt/clients/user_X_Y/ si hay datos
ls -la /opt/clients/user_X_Y/

# Escalar el incidente a revisión manual antes de recrear
```

## Fix permanente
En `collect_resource_usage.py`, añadir manejo de `docker.errors.NotFound` dentro del loop:

```python
import docker.errors

for hosting in active_hostings:
    try:
        stats = docker_client.containers.get(hosting.container_name).stats(stream=False)
        # ... procesar stats
    except docker.errors.NotFound:
        logger.warning(
            "Container not found in Docker, skipping metrics collection",
            extra={"container_name": hosting.container_name, "hosting_id": hosting.id}
        )
        continue  # CRÍTICO: no raise, solo skip
    except Exception as e:
        logger.error(
            "Unexpected error collecting metrics",
            extra={"container_name": hosting.container_name, "error": str(e)}
        )
        continue
```

Adicionalmente: añadir un job de reconciliación que detecte contenedores en BD marcados como activos pero inexistentes en Docker y los marque como `orphaned` para revisión humana.

## Señales para detección automática
- Log pattern: `No such container: user_` en logs del scheduler
- Log pattern: `Error: No such container`
- Ausencia de nuevos registros en tabla de métricas durante > 10 minutos
- Alerta: "metrics collection gap" si no hay datos en los últimos 2 ciclos de recolección

## Auto-remediation permitido
- `skip_missing_container_in_metrics`: El colector puede y debe continuar con los demás hostings cuando un contenedor no se encuentra. Esta es la remediación automática correcta: skip + log + continue.

## Auto-remediation prohibido
- `delete_hosting_record_when_container_missing`: Nunca eliminar el registro de hosting de la BD automáticamente. El contenedor puede ser temporal o estar en proceso de recreación.
- `stop_all_metric_collection`: Detener toda la recolección de métricas como respuesta al error es peor que el problema original.

## Dashboard esperado
- **Resource metrics**: datos continuos para todos los hostings activos con contenedor real.
- **Scheduler logs**: warnings de `Container not found` para contenedores fantasma, pero sin errores que interrumpan el ciclo.
- **Metrics gap**: 0 gaps de más de 2 ciclos de recolección.
- **Orphaned containers**: alerta en dashboard de admin si hay hostings en BD sin contenedor Docker.

## RAG usage
Recuperar con: `No such container collector crash`, `resource collector loop break`, `missing container metrics skip`.
Contexto relevante: `collect_resource_usage.py`, `app/services/scheduler_runner.py`, modelo `Hosting` (campo `container_name`, `status`).

## Tests/Chaos
```python
# Test: colector no falla si un contenedor no existe
def test_collector_skips_missing_container(mocker, db_session, test_hosting):
    # Simular que Docker no encuentra el contenedor
    mock_docker = mocker.patch("docker.DockerClient.containers")
    mock_docker.get.side_effect = docker.errors.NotFound("No such container")

    # El colector NO debe lanzar excepción; debe skipear y continuar
    from app.services.collect_resource_usage import collect_all
    result = collect_all(db_session)  # debe completar sin excepción
    assert result is not None

# Chaos: eliminar un contenedor manualmente y verificar que el próximo ciclo no explota
# docker rm -f user_test_wordpress
# Esperar el próximo ciclo del scheduler
# Verificar logs: debe aparecer warning, no error fatal
```
