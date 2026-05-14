---
incident_id: CLIENT_DIR_RESIDUAL_AFTER_TERMINATE
incident_type: data_residual
severity: low
status: confirmed
validated: true
auto_repair_allowed: false
safe_actions:
  - audit_residual_client_dirs
forbidden_actions:
  - delete_client_data_without_snapshot
  - auto_cleanup_without_human_review
signatures:
  - "/opt/clients/ residual"
  - "directory exists after terminate"
---

# CLIENT_DIR_RESIDUAL_AFTER_TERMINATE

## Síntoma
Después de terminar un hosting correctamente (contenedor detenido y eliminado, registro en BD marcado como `terminated`), el directorio `/opt/clients/{container_name}/` permanece en el servidor. El directorio contiene datos del cliente (archivos WordPress, base de datos, uploads, logs).

## Impacto
- **Privacidad y retención**: El directorio contiene datos del cliente que deberían purgarse según la política de retención.
- **Disco**: Cada directorio residual consume espacio en disco en el servidor (puede ser varios GB por hosting).
- **Riesgo de reutilización**: Si el `container_name` se reutiliza para un nuevo hosting, el directorio residual puede causar conflictos o exponer datos del cliente anterior.
- **Cumplimiento**: Posible incumplimiento de GDPR o política de privacidad si los datos se conservan indefinidamente tras la baja.
- No hay impacto inmediato en el servicio de otros clientes.

## Evidencia
```bash
# Listar directorios en /opt/clients/
ls -la /opt/clients/ | head -30

# Comparar con contenedores activos en Docker
docker ps --format "{{.Names}}" | sort > /tmp/active_containers.txt
ls /opt/clients/ | sort > /tmp/client_dirs.txt
comm -13 /tmp/active_containers.txt /tmp/client_dirs.txt
# Las líneas resultantes son directorios residuales (existen en /opt/clients/ pero no como contenedor activo)

# Verificar estado en BD
docker compose exec app python -c "
from app.db.session import get_db
from sqlalchemy import text
db = next(get_db())
result = db.execute(text(\"\"\"
  SELECT container_name, status, terminated_at
  FROM hostings
  WHERE container_name IN ('user_X_wordpress', 'user_X_mariadb')
\"\"\"))
for row in result: print(row)
"
```

## Causa raíz
El proceso de terminación de hosting en HostingGuard:
1. Detiene y elimina los contenedores Docker ✓
2. Actualiza el estado en la BD a `terminated` ✓
3. Elimina las reglas de Traefik (archivo YAML en `/opt/traefik-dynamic/`) ✓
4. **NO elimina el directorio `/opt/clients/{container_name}/`** ✗ — paso faltante en el pipeline de terminación.

Esto puede ser intencional (retención de datos por un período de gracia antes de purgar) o un bug de omisión en el executor de terminación.

## Diagnósticos equivocados
- **"La terminación falló"**: La terminación puede haber sido exitosa en todos sus pasos excepto la limpieza del directorio. Verificar el estado en BD y Docker antes de asumir fallo.
- **"El directorio está en uso por otro proceso"**: Verificar con `lsof /opt/clients/user_X/` pero generalmente el directorio queda libre tras eliminar el contenedor.
- **"Es un problema de permisos"**: El directorio sí se puede borrar; simplemente el pipeline no lo hace.

## Diagnóstico rápido
```bash
# 1. Auditoría completa de directorios residuales
echo "=== Directorios en /opt/clients/ ==="
ls /opt/clients/ | wc -l

echo "=== Contenedores activos en Docker ==="
docker ps --format "{{.Names}}" | wc -l

echo "=== Hostings activos en BD ==="
docker compose exec app python -c "
from app.db.session import get_db
from sqlalchemy import text
db = next(get_db())
result = db.execute(text(\"SELECT COUNT(*) FROM hostings WHERE status='active'\"))
print(list(result))
"

# 2. Identificar directorios sin contenedor activo correspondiente
for dir in /opt/clients/*/; do
    name=$(basename "$dir")
    if ! docker inspect "$name" &>/dev/null 2>&1; then
        size=$(du -sh "$dir" 2>/dev/null | cut -f1)
        echo "RESIDUAL: $name (size: $size)"
    fi
done

# 3. Verificar estado en BD para cada residual
# (ejecutar para cada directorio identificado como residual)
```

## Solución manual
**IMPORTANTE**: Nunca eliminar directorios de cliente sin revisión humana y sin snapshot previo.

### Proceso seguro de limpieza:
```bash
CONTAINER_NAME="user_X_wordpress"
CLIENT_DIR="/opt/clients/${CONTAINER_NAME}"

# Paso 1: Confirmar que el hosting está terminado en BD
docker compose exec app python -c "
from app.db.session import get_db
from sqlalchemy import text
db = next(get_db())
result = db.execute(text(\"SELECT id, status, terminated_at FROM hostings WHERE container_name=:cn\"), {'cn': '${CONTAINER_NAME}'})
print(list(result))
"
# Debe mostrar status='terminated' y terminated_at con fecha

# Paso 2: Verificar que el contenedor no existe
docker inspect "${CONTAINER_NAME}" 2>&1  # Debe decir "No such object"

# Paso 3: Crear snapshot antes de borrar
SNAPSHOT_DATE=$(date +%Y%m%d_%H%M%S)
SNAPSHOT_PATH="/opt/backups/terminated_clients/${CONTAINER_NAME}_${SNAPSHOT_DATE}.tar.gz"
mkdir -p /opt/backups/terminated_clients/
tar -czf "${SNAPSHOT_PATH}" -C /opt/clients/ "${CONTAINER_NAME}/"
echo "Snapshot created: ${SNAPSHOT_PATH}"
ls -lh "${SNAPSHOT_PATH}"

# Paso 4: Eliminar el directorio (SOLO tras confirmación del snapshot)
rm -rf "${CLIENT_DIR}"
echo "Removed: ${CLIENT_DIR}"

# Paso 5: Registrar la limpieza en el audit log
docker compose exec app python -c "
from app.services.audit_service import log_action
log_action(
    action='client_dir_purged',
    target='${CONTAINER_NAME}',
    details={'snapshot': '${SNAPSHOT_PATH}', 'performed_by': 'admin_manual'}
)
"
```

### Script de auditoría masiva (solo listado, sin borrar):
```bash
#!/bin/bash
# scripts/audit_residual_client_dirs.sh
echo "=== RESIDUAL CLIENT DIRECTORIES AUDIT ==="
echo "Date: $(date)"
echo ""
for dir in /opt/clients/*/; do
    name=$(basename "$dir")
    size=$(du -sh "$dir" 2>/dev/null | cut -f1)
    # Verificar si hay contenedor activo
    if docker inspect "$name" &>/dev/null 2>&1; then
        status="ACTIVE"
    else
        status="RESIDUAL"
    fi
    echo "${status}: ${name} (${size})"
done
```

## Fix permanente
1. Añadir la eliminación del directorio al pipeline de terminación de hosting:
   ```python
   # En app/executors/terminate_hosting.py (o equivalente)
   import shutil
   import os

   CLIENT_DIR = f"/opt/clients/{container_name}"

   # Después de eliminar el contenedor:
   if os.path.exists(CLIENT_DIR):
       # Crear snapshot antes de borrar (política de retención: 30 días)
       snapshot_path = create_snapshot(CLIENT_DIR, container_name)
       shutil.rmtree(CLIENT_DIR)
       logger.info(f"Removed client dir: {CLIENT_DIR}, snapshot: {snapshot_path}")
       audit_log("client_dir_purged", container_name, snapshot_path)
   ```

2. Definir y documentar la **política de retención de datos** de clientes terminados:
   - Snapshot comprimido guardado en `/opt/backups/terminated_clients/`
   - Retención del snapshot: N días (definir según política de privacidad)
   - Purga automática de snapshots vencidos: job diario en scheduler.

3. Añadir un job de reconciliación en el scheduler que detecte directorios residuales y los reporte (sin borrar automáticamente).

## Señales para detección automática
- Directorio en `/opt/clients/` sin contenedor Docker correspondiente y hosting en BD con `status='terminated'`
- Disco del servidor aumenta tras terminar hostings (en lugar de liberar espacio)
- Alerta semanal: count de directorios residuales > 0

## Auto-remediation permitido
- `audit_residual_client_dirs`: Ejecutar el script de auditoría para listar y reportar directorios residuales. No borra nada; solo informa.

## Auto-remediation prohibido
- `delete_client_data_without_snapshot`: Nunca eliminar datos de cliente sin crear un snapshot previo verificado. Los datos pueden ser necesarios para disputa de facturación o recuperación solicitada.
- `auto_cleanup_without_human_review`: La eliminación de directorios de cliente debe ser siempre aprobada por un humano. El impacto de borrar datos incorrectamente es irreversible.

## Dashboard esperado
- **Residual dirs**: 0 directorios en `/opt/clients/` sin contenedor activo correspondiente tras 30 días de la terminación.
- **Disk freed**: el disco del servidor debe disminuir proporcionalmente al tamaño de los hostings terminados.
- **Audit log**: cada purga de directorio de cliente debe quedar registrada.

## RAG usage
Recuperar con: `client directory residual terminate cleanup`, `/opt/clients/ not deleted after terminate`, `data retention terminated hosting`.
Contexto relevante: executor de terminación de hosting, política de retención de datos, scheduler de purga.

## Tests/Chaos
```python
# Test: terminar un hosting limpia el directorio /opt/clients/
def test_terminate_removes_client_dir(tmp_path, mocker, test_hosting):
    # Crear directorio de cliente de prueba
    client_dir = tmp_path / test_hosting.container_name
    client_dir.mkdir()
    (client_dir / "wp-content").mkdir()

    mocker.patch("CLIENTS_BASE_DIR", str(tmp_path))

    # Ejecutar terminación
    terminate_hosting(test_hosting.id)

    # El directorio debe haberse eliminado (o movido a backup)
    assert not client_dir.exists()

# Chaos: terminar 10 hostings y verificar que /opt/clients/ no crece
# Antes: medir du -sh /opt/clients/
# Terminar 10 hostings
# Después: medir du -sh /opt/clients/ → debe haber disminuido
```
