---
incident_id: RESOURCE_DISK_DF_OVERREPORT
incident_type: metrics_false_positive
severity: low
status: confirmed
validated: true
auto_repair_allowed: false
safe_actions: []
forbidden_actions:
  - delete_container_to_free_disk
  - auto_scale_down_on_false_disk_alert
signatures:
  - "disk usage.*%.*df"
  - "overlay.*disk"
---

# RESOURCE_DISK_DF_OVERREPORT

## Síntoma
El dashboard de recursos muestra el disco de un hosting al 90-100% de uso, pero los archivos reales del cliente suman solo el 20-30% del límite asignado. El colector de recursos registra valores inflados. Se pueden disparar alertas críticas de disco falsas.

## Impacto
- Alertas críticas de disco falsas que alarman al cliente y al equipo de operaciones.
- Si hay auto-scaling o throttling basado en métricas de disco, puede aplicarse incorrectamente.
- No hay impacto real en el servicio del cliente: el disco real no está lleno.
- Bajo, pero puede generar trabajo operacional innecesario (investigaciones, tickets de soporte).

## Evidencia
```bash
# Dentro del contenedor, df reporta alto uso:
docker exec user_X_wordpress df -h /
# Filesystem      Size  Used Avail Use%
# overlay         20G   18G  2.0G  90%   ← inflado

# Pero los archivos reales son mucho menores:
docker exec user_X_wordpress du -sh /var/www/html/
# 2.1G    /var/www/html/

# Y en la BD:
# resource_metrics.disk_usage_percent = 90  (incorrecto)
# resource_metrics.disk_used_bytes = 18000000000  (incorrecto)
```

## Causa raíz
Los contenedores Docker usan el driver de filesystem **overlay2** (o overlay). El comando `df` dentro del contenedor reporta el espacio del filesystem overlay, que incluye:

1. **Capas de imagen base**: las capas de la imagen Docker (WordPress, PHP, nginx, MariaDB) se cuentan como parte del espacio usado.
2. **Capas de escritura**: solo la capa superior (writable layer) contiene los datos reales del cliente.
3. **Shared layers**: múltiples contenedores comparten las mismas capas de imagen, pero `df` las reporta como usadas por cada contenedor individualmente.

El resultado es que `df` dentro del contenedor sobreestima el uso de disco real del cliente.

La métrica correcta es el tamaño de la **capa de escritura** del contenedor, no el total del overlay filesystem.

## Diagnósticos equivocados
- **"El contenedor realmente está lleno"**: Verificar con `du -sh` dentro del contenedor; si es mucho menor que lo que reporta `df`, es overreporting.
- **"Hay un proceso que está llenando el disco"**: Primero verificar si el problema es de medición o real. Si `du` y `df` coinciden, el disco sí está lleno.
- **"Hay una fuga de logs"**: Posible, pero verificar primero que no sea overreporting de overlay.
- **"El colector está buggeado"**: El colector reporta lo que `df` dice; el problema está en la fuente de la métrica, no en el colector.

## Diagnóstico rápido
```bash
CONTAINER_NAME="user_X_wordpress"

# 1. Comparar df vs du dentro del contenedor
echo "=== df reporta ==="
docker exec "${CONTAINER_NAME}" df -h /

echo "=== du en /var/www ==="
docker exec "${CONTAINER_NAME}" du -sh /var/www/html/ 2>/dev/null || true

echo "=== du en /var/lib/mysql (si tiene MariaDB) ==="
docker exec "${CONTAINER_NAME}" du -sh /var/lib/mysql/ 2>/dev/null || true

# 2. Ver el tamaño real de la writable layer desde el host
docker inspect "${CONTAINER_NAME}" --format='{{.SizeRootFs}} {{.SizeRw}}'
# SizeRootFs = total incluye imagen base (puede ser enorme)
# SizeRw = solo la capa de escritura del contenedor (el dato correcto)

# 3. Comparar con la métrica almacenada en BD
docker compose exec app python -c "
from app.db.session import get_db
from sqlalchemy import text
db = next(get_db())
result = db.execute(text(\"\"\"
  SELECT disk_usage_percent, disk_used_bytes, recorded_at
  FROM resource_metrics
  WHERE hosting_id=X
  ORDER BY recorded_at DESC LIMIT 5
\"\"\"))
for row in result: print(row)
"
```

## Solución manual
### Corrección de la métrica de disco:
El colector debe usar `docker inspect` con `SizeRw` en lugar de `df`:

```bash
# Verificar el tamaño real de la writable layer:
docker inspect user_X_wordpress --format='{{.SizeRw}}'
# Este es el número correcto de bytes usados por el cliente

# Calcular el porcentaje correcto:
DISK_LIMIT_BYTES=10737418240  # 10 GB (límite del plan)
SIZE_RW=$(docker inspect user_X_wordpress --format='{{.SizeRw}}')
echo "Real usage: $((SIZE_RW * 100 / DISK_LIMIT_BYTES))%"
```

### Para suprimir alertas falsas mientras se investiga:
```bash
# Marcar la alerta como falso positivo en el sistema de alertas
# (acción manual en el dashboard, no scripted)
# No escalar a cliente hasta verificar que el disco real no está lleno
```

## Fix permanente
Actualizar `collect_resource_usage.py` para obtener el uso de disco correcto:

```python
import docker

client = docker.DockerClient()

def get_disk_usage_for_container(container_name: str, disk_limit_bytes: int) -> dict:
    """
    Usa SizeRw de docker inspect para medir solo la writable layer.
    Más preciso que df dentro del contenedor para medir uso real del cliente.
    """
    try:
        container = client.containers.get(container_name)
        # size=True requiere un inspect especial; alternativamente usar df con --output
        # El método más confiable: docker system df -v para el contenedor específico
        info = client.containers.get(container_name).stats(stream=False)
        # O usar subprocess con docker inspect:
        import subprocess
        result = subprocess.run(
            ["docker", "inspect", "--size", "--format", "{{.SizeRw}}", container_name],
            capture_output=True, text=True, check=True
        )
        size_rw = int(result.stdout.strip())
        pct = (size_rw / disk_limit_bytes) * 100 if disk_limit_bytes > 0 else 0
        return {"disk_used_bytes": size_rw, "disk_usage_percent": round(pct, 2)}
    except Exception as e:
        logger.warning(f"Could not get SizeRw for {container_name}: {e}")
        # Fallback a df (con la limitación conocida de overreporting)
        return get_disk_usage_via_df(container_name, disk_limit_bytes)
```

Documentar en el código la diferencia entre `SizeRootFs` y `SizeRw`:
- `SizeRootFs`: incluye capas de imagen compartida. NO usar para medir uso del cliente.
- `SizeRw`: solo la capa de escritura del contenedor. USAR para medir uso del cliente.

## Señales para detección automática
- `disk_usage_percent > 85%` con `du_actual_bytes < disk_limit * 0.4` (discrepancia > 2x)
- Patrón: múltiples contenedores con el mismo porcentaje de disco alto (indica overreporting sistémico)
- Alerta de disco que no coincide con el tamaño de archivos reportado por `du`

## Auto-remediation permitido
Ninguna. La corrección requiere un cambio en el colector de métricas y redeploy.

## Auto-remediation prohibido
- `delete_container_to_free_disk`: Nunca eliminar un contenedor porque el dashboard muestra disco alto. Verificar primero si es un falso positivo de overlay.
- `auto_scale_down_on_false_disk_alert`: No ejecutar acciones de throttling o scale-down basadas en alertas de disco sin verificar que el uso real es elevado.

## Dashboard esperado
- **Disk usage**: basado en `SizeRw` del contenedor (writable layer), no en `df` del overlay filesystem.
- **Alertas de disco**: solo cuando el uso real (`SizeRw`) supera el umbral, no por sobreestimación de overlay.
- **Discrepancia métrica**: 0 casos donde el dashboard muestra >80% y `du` muestra <40%.

## RAG usage
Recuperar con: `disk overreport overlay filesystem df container`, `SizeRw SizeRootFs docker inspect disk metrics`, `false disk alert overlay2`.
Contexto relevante: `collect_resource_usage.py`, tabla `resource_metrics`, configuración de alertas de disco.

## Tests/Chaos
```python
# Test: el colector usa SizeRw, no df total
def test_disk_metric_uses_size_rw(mocker):
    # Mockear docker inspect para retornar SizeRw conocido
    mock_inspect = mocker.patch("subprocess.run")
    mock_inspect.return_value.stdout = "1073741824\n"  # 1 GB

    disk_limit = 10 * 1024**3  # 10 GB
    result = get_disk_usage_for_container("test_container", disk_limit)

    assert result["disk_used_bytes"] == 1073741824
    assert abs(result["disk_usage_percent"] - 10.0) < 0.1

# Chaos: verificar que una alerta de disco alta se correlaciona con du real
# Si disk_usage_percent > 80 pero du < 40% del límite → marcar como falso positivo
```
