---
incident_id: ZIP_IMPORT_PERMISSION_DENIED
incident_type: operational
severity: medium
status: confirmed
validated: true
auto_repair_allowed: false
safe_actions:
  - fix_import_tmp_permissions
forbidden_actions:
  - chmod_777_entire_opt_clients
  - skip_permission_check_on_upload
signatures:
  - "Permission denied: /tmp/hg_imports"
  - "Permission denied: /opt/clients/"
  - "PermissionError: [Errno 13] Permission denied"
  - "import_dir_not_writable"
  - "503 import_dir_not_writable"
---

# ZIP_IMPORT_PERMISSION_DENIED

## Síntoma
El endpoint de importación de sitio via ZIP (`POST /api/tenants/{id}/import-zip` o similar) devuelve error 503 con código `import_dir_not_writable`, o la operación de escritura de archivos falla con `Permission denied` durante el proceso de importación. El administrador o el inquilino no puede subir un nuevo sitio.

## Impacto
- El proceso de importación de sitios via ZIP está completamente bloqueado para el inquilino afectado.
- Si el directorio `/tmp/hg_imports` no es escribible, todos los imports fallan independientemente del inquilino.
- Si sólo `/opt/clients/{container_name}/` no es escribible, sólo ese inquilino está afectado.
- El contenido del sitio actual (si existe) no se ve afectado — sólo el proceso de actualización/importación falla.

## Evidencia
```bash
# Verificar permisos del directorio de imports temporales
ls -la /tmp/hg_imports 2>/dev/null || echo "DIRECTORIO /tmp/hg_imports NO EXISTE"

# Verificar permisos del directorio del cliente
ls -la /opt/clients/mi-academia/ 2>/dev/null || echo "DIRECTORIO NO EXISTE"

# Ver el UID/GID con el que corre el contenedor de la app
docker inspect app --format='User={{.Config.User}}'
docker exec app id 2>/dev/null

# Verificar el propietario y permisos de /opt/clients/
ls -la /opt/clients/ 2>/dev/null

# Ver los logs de la app al momento del error
docker compose -f /opt/deploy/docker-compose.yml logs --tail=50 app 2>&1 | grep -i "permission\|errno 13\|import"

# Intentar escribir en el directorio como el usuario del contenedor (diagnóstico)
docker exec app touch /opt/clients/mi-academia/test_write 2>&1 || echo "No se puede escribir"
docker exec app rm /opt/clients/mi-academia/test_write 2>/dev/null || true
```

## Causa raíz
El contenedor de la aplicación FastAPI corre como usuario no-root (ej. uid=1000, gid=1000 o usuario `appuser`). Los directorios `/tmp/hg_imports` (directorio temporal de extracción de ZIP) y `/opt/clients/{container_name}/` (destino final de los archivos del sitio) son creados por root en el host o por otros procesos, y no tienen permisos de escritura para el usuario del contenedor. El endpoint de la API verifica la escribibilidad antes de aceptar el upload y devuelve 503 con código `import_dir_not_writable` si falla la verificación. Si la verificación está desactivada, el error aparece durante la escritura y es un `PermissionError` de Python.

## Diagnósticos equivocados
- **"El ZIP está corrupto"** — Si el error es de permisos, el problema ocurre antes de extraer el ZIP. Un ZIP corrupto produciría un error diferente (`BadZipFile`, no `PermissionError`).
- **"La cuota de disco está llena"** — Un disco lleno produce `OSError: [Errno 28] No space left on device`, no `PermissionError`. Verificar con `df -h`.
- **"El contenedor de la app está caído"** — Si el endpoint devuelve 503 con cuerpo JSON `import_dir_not_writable`, la app está corriendo. Un contenedor caído no devolvería JSON estructurado.
- **"El inquilino tiene un plan que no incluye importación"** — El error de permisos es a nivel de filesystem, no de lógica de negocio. El error de plan sería 403, no 503.
- **"Hay que reiniciar el contenedor de la app"** — Los permisos de filesystem no cambian con un reinicio del contenedor.

## Diagnóstico rápido
```bash
echo "=== Diagnóstico ZIP_IMPORT_PERMISSION_DENIED ==="

# 1. Directorio temporal
echo "[TMP] /tmp/hg_imports:"
ls -la /tmp/hg_imports 2>/dev/null || echo "  NO EXISTE"

# 2. UID del proceso de la app
echo "[APP] Usuario del contenedor app:"
docker exec app id 2>/dev/null || echo "  No se puede acceder al contenedor app"
APP_UID=$(docker inspect app --format='{{.Config.User}}' 2>/dev/null || echo "unknown")
echo "  User config: $APP_UID"

# 3. Permisos de /opt/clients/
echo "[CLIENTS] Permisos de /opt/clients/:"
ls -la /opt/clients/ 2>/dev/null | head -10

# 4. Test de escritura desde el contenedor
echo "[WRITE TEST] Prueba de escritura desde app container:"
docker exec app sh -c "touch /tmp/hg_imports/test_write 2>&1 && echo 'OK: /tmp/hg_imports escribible' && rm /tmp/hg_imports/test_write" 2>/dev/null \
  || echo "FAIL: /tmp/hg_imports no escribible desde container"

docker exec app sh -c "touch /opt/clients/mi-academia/test_write 2>&1 && echo 'OK: /opt/clients/mi-academia escribible' && rm /opt/clients/mi-academia/test_write" 2>/dev/null \
  || echo "FAIL: /opt/clients/mi-academia no escribible desde container"

# 5. Espacio en disco
echo "[DISK] Espacio disponible:"
df -h /opt/clients/ /tmp/ 2>/dev/null | head -5
```

## Solución manual
```bash
# PASO 1: Obtener el UID del usuario del contenedor de la app
APP_UID=$(docker exec app id -u 2>/dev/null || echo "1000")
APP_GID=$(docker exec app id -g 2>/dev/null || echo "1000")
echo "UID de la app: $APP_UID, GID: $APP_GID"

# PASO 2: Crear y corregir el directorio temporal de imports
# Si no existe, crearlo:
mkdir -p /tmp/hg_imports

# Cambiar propietario al usuario de la app:
chown "${APP_UID}:${APP_GID}" /tmp/hg_imports
chmod 755 /tmp/hg_imports

# Verificar:
ls -la /tmp/ | grep hg_imports

# PASO 3: Corregir permisos del directorio del cliente específico
TENANT="mi-academia"  # ajustar
mkdir -p "/opt/clients/${TENANT}"
chown "${APP_UID}:${APP_GID}" "/opt/clients/${TENANT}"
chmod 755 "/opt/clients/${TENANT}"

# Verificar:
ls -la "/opt/clients/${TENANT}"

# PASO 4: Verificar que el contenedor puede escribir ahora
docker exec app sh -c "touch /tmp/hg_imports/test_$(date +%s) && echo OK && rm /tmp/hg_imports/test_*" 2>/dev/null
docker exec app sh -c "touch /opt/clients/${TENANT}/test_$(date +%s) && echo OK && rm /opt/clients/${TENANT}/test_*" 2>/dev/null

# PASO 5: Re-intentar el import via API
# (el cliente puede volver a subir el ZIP)
echo "[INFO] Los permisos han sido corregidos. El cliente puede reintentar la importación."

# NOTA: NO hacer chmod 777 en /opt/clients/ completo
# Correcto: corregir sólo el directorio específico del inquilino afectado
# Incorrecto: chmod 777 /opt/clients/  (expone datos de todos los inquilinos)
```

## Fix permanente
El proceso de provisioning de inquilinos debe crear el directorio `/opt/clients/{container_name}/` con el propietario correcto (UID del usuario de la app) como parte de la creación del contenedor. Esto debe ocurrir en el host, no dentro del contenedor.

El directorio `/tmp/hg_imports` debe ser creado como parte del script de bootstrap del servidor con los permisos correctos, o creado automáticamente por la app al arrancar con permisos correctos.

El endpoint de importación debe verificar la escribibilidad del directorio de destino antes de aceptar el upload y devolver 503 con `code: import_dir_not_writable` si falla:
```python
import os
dest_dir = f"/opt/clients/{container_name}"
if not os.access(dest_dir, os.W_OK):
    raise HTTPException(
        status_code=503,
        detail={"code": "import_dir_not_writable", "dir": dest_dir}
    )
```

## Señales para detección automática
- Log pattern: `"PermissionError.*opt/clients"` o `"PermissionError.*hg_imports"` en logs de la app.
- Response pattern: endpoint de import devuelve 503 con body `{"code": "import_dir_not_writable"}`.
- Verificación periódica: script que verifica que el contenedor `app` puede escribir en `/tmp/hg_imports` y en `/opt/clients/` (muestreo de directorios).

## Auto-remediation permitido
- Crear `/tmp/hg_imports` con permisos correctos si no existe (acción: `fix_import_tmp_permissions`). Esta es una operación de bajo riesgo en el directorio temporal.

## Auto-remediation prohibido
- `chmod 777 /opt/clients/` — cambia permisos de directorios de todos los inquilinos, exponiendo datos entre tenants.
- Omitir la verificación de permisos en el endpoint de upload (`skip_permission_check_on_upload`). Esto causaría errores de Python no controlados durante el upload.
- Ejecutar el contenedor de la app como root para evitar el problema de permisos — violación de principio de mínimo privilegio.

## Dashboard esperado
- Badge **MEDIUM** en el panel del inquilino afectado: "Import failed — permission error".
- En el historial de operaciones del inquilino: "ZIP import failed — status: 503, code: import_dir_not_writable".
- Alerta en `system_incidents` con `severity='medium'`, `incident_type='import_error'`.
- No bloquea el badge de salud del sitio si el sitio actual está sirviendo contenido correctamente.

## RAG usage
Cuando el administrador reporte "error al importar ZIP" o "el cliente no puede subir su sitio", la IA debe verificar primero si el error es 503 con código `import_dir_not_writable` (permisos) o si es otro tipo de error (ZIP corrupto, cuota llena, etc.). Si es de permisos, la IA debe guiar a verificar el UID del contenedor `app` y los permisos de los directorios de destino. La IA debe enfatizar que la solución es cambiar el propietario con `chown`, no `chmod 777` en el directorio completo.

## Tests/Chaos
```bash
#!/bin/bash
# chaos/test_zip_import_permission_denied.sh
# Simula el error de permisos en el directorio de imports

set -euo pipefail

TMP_DIR="/tmp/hg_imports"
APP_UID=$(docker exec app id -u 2>/dev/null || echo "1000")
APP_GID=$(docker exec app id -g 2>/dev/null || echo "1000")

echo "[CHAOS] Cambiar propietario de /tmp/hg_imports a root"
chown root:root "$TMP_DIR" 2>/dev/null || sudo chown root:root "$TMP_DIR"
chmod 700 "$TMP_DIR"

echo "[DETECT] Intentar escribir desde el contenedor app"
if docker exec app sh -c "touch ${TMP_DIR}/test_chaos 2>&1"; then
  echo "[WARN] El contenedor puede escribir aunque el directorio es de root (quizás corre como root)"
else
  echo "[OK] Escritura denegada — error de permisos correctamente detectado"
fi

echo "[DETECT] Simular llamada al endpoint de import"
# Requiere un ZIP de prueba y token de admin
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "http://localhost:8000/api/tenants/test-tenant/import-zip" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -F "file=@/tmp/test.zip" 2>/dev/null || echo "000")
echo "  HTTP response: $RESPONSE (esperado 503)"

echo "[RECOVER] Restaurar permisos correctos"
chown "${APP_UID}:${APP_GID}" "$TMP_DIR"
chmod 755 "$TMP_DIR"

echo "[VERIFY] Escritura restaurada desde app container"
docker exec app sh -c "touch ${TMP_DIR}/test_restored && rm ${TMP_DIR}/test_restored && echo OK" 2>/dev/null
```
