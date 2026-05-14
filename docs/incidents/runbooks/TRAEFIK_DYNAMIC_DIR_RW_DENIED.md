---
incident_id: TRAEFIK_DYNAMIC_DIR_RW_DENIED
incident_type: infrastructure
severity: critical
status: confirmed
validated: true
auto_repair_allowed: false
safe_actions:
  - fix_traefik_dynamic_dir_permissions
forbidden_actions:
  - chmod_777_entire_opt
  - mount_traefik_dynamic_as_world_writable_permanently
signatures:
  - "Permission denied: /opt/traefik-dynamic/"
  - "PermissionError: [Errno 13] Permission denied: '/opt/traefik-dynamic/"
  - "OSError: [Errno 13] Permission denied writing traefik"
  - "failed to write tenant route: permission denied"
  - "cannot create file in /opt/traefik-dynamic/"
---

# TRAEFIK_DYNAMIC_DIR_RW_DENIED

## Síntoma
El backend FastAPI o el scheduler no pueden escribir archivos en `/opt/traefik-dynamic/`. Al crear, actualizar o eliminar inquilinos, el proceso falla con `Permission denied` al intentar escribir el YAML de configuración de Traefik. Los logs de la app muestran `PermissionError: [Errno 13] Permission denied: '/opt/traefik-dynamic/...'`. Las rutas de inquilinos existentes siguen funcionando (Traefik lee los archivos ya presentes), pero no se pueden crear ni actualizar rutas nuevas.

## Impacto
- El provisioning de nuevos inquilinos falla completamente — no se puede crear la ruta de Traefik.
- Las actualizaciones de rutas existentes (cambio de subdominio, cambio de puerto, migración de middleware) fallan.
- La eliminación de rutas también falla — un inquilino dado de baja seguirá teniendo su ruta activa en Traefik.
- El scheduler no puede ejecutar jobs que requieran escribir configuración de Traefik (ej. regeneración masiva de rutas).
- Las rutas de inquilinos existentes **siguen funcionando** — el problema afecta sólo a escrituras, no a lecturas.

## Evidencia
```bash
# Verificar los permisos actuales del directorio
ls -la /opt/traefik-dynamic/

# Ver el propietario y modo del directorio
stat /opt/traefik-dynamic/

# Ver el UID con el que corre el contenedor de la app
docker inspect app --format='User={{.Config.User}}'
docker exec app id 2>/dev/null

# Ver el UID con el que corre el contenedor del scheduler
docker inspect hg_scheduler --format='User={{.Config.User}}' 2>/dev/null
docker exec hg_scheduler id 2>/dev/null

# Intentar escribir en el directorio desde el contenedor de la app
docker exec app sh -c "touch /opt/traefik-dynamic/test_write_$(date +%s) 2>&1 && echo OK || echo FAIL"

# Ver logs de la app buscando errores de permisos
docker compose -f /opt/deploy/docker-compose.yml logs --tail=100 app 2>&1 \
  | grep -i "permission\|errno 13\|traefik-dynamic"

# Ver el mount del directorio en docker-compose
grep -A 3 "traefik-dynamic" /opt/deploy/docker-compose.yml
```
Salida esperada del problema:
```
drwxr-xr-x  2 root root 4096 Jan 15 10:00 /opt/traefik-dynamic/
# Y la app corre como uid=1000, que no tiene permiso de escritura
```

## Causa raíz
El directorio `/opt/traefik-dynamic/` fue creado en el host con `mkdir` por el usuario `root` y tiene permisos `755` (owner: root, group: root). El directorio está montado como `rw` en los contenedores de la app y del scheduler via `docker-compose.yml`:
```yaml
volumes:
  - /opt/traefik-dynamic:/etc/traefik/dynamic:rw
```
Sin embargo, los contenedores corren como usuario no-root (ej. `uid=1000`). En Docker con bind mounts, los permisos del directorio en el **host** determinan si el proceso del contenedor puede escribir. El contenedor no puede escribir en el directorio porque el propietario es root (uid=0) y el modo `755` no da permisos de escritura al "others" (los demás usuarios, incluido uid=1000 del contenedor).

El flag `:rw` en el mount de Docker **no** otorga permisos de escritura a nivel de filesystem del host — sólo controla si el mount es read-write o read-only desde la perspectiva de Docker. Los permisos del host prevalecen.

## Diagnósticos equivocados
- **"El volumen está montado como :rw, por qué falla"** — `:rw` es el modo de mount de Docker, no los permisos de filesystem del host. Root en el host puede escribir; uid=1000 (app) no puede aunque el mount sea `:rw`.
- **"Hay que cambiar el Dockerfile para que la app corra como root"** — Correr como root viola el principio de mínimo privilegio y es una vulnerabilidad de seguridad. La solución correcta es cambiar los permisos del directorio en el host.
- **"Traefik tampoco puede escribir en el directorio"** — Traefik sólo lee el directorio (no escribe). El file watcher de Traefik sólo necesita permisos de lectura. El problema es que la APP no puede escribir.
- **"El directorio no existe"** — Si existiera el error `"No such file or directory"`, sería un problema diferente. `Permission denied` significa que el directorio existe pero el usuario no tiene permiso de escritura.
- **"Hay que cambiar el :rw por otra opción de Docker"** — No existe una opción de Docker que eleve permisos de filesystem del host. La solución está en el host, no en la configuración de Docker.

## Diagnóstico rápido
```bash
echo "=== Diagnóstico TRAEFIK_DYNAMIC_DIR_RW_DENIED ==="

TRAEFIK_DIR="/opt/traefik-dynamic"

# 1. Permisos del directorio en el host
echo "[HOST] Permisos de $TRAEFIK_DIR:"
ls -la "$TRAEFIK_DIR" | head -3
stat "$TRAEFIK_DIR" | grep -E "Uid|Gid|Access"

# 2. UID del contenedor de la app
echo "[APP] UID del proceso en contenedor app:"
APP_UID=$(docker exec app id -u 2>/dev/null || echo "no_access")
APP_USER=$(docker exec app id 2>/dev/null || echo "no_access")
echo "  $APP_USER"

# 3. Test de escritura
echo "[WRITE TEST] Prueba de escritura desde contenedor app:"
docker exec app sh -c "touch ${TRAEFIK_DIR}/.write_test_$(date +%s) 2>&1" \
  && echo "  [OK] Escritura permitida" \
  || echo "  [FAIL] Escritura denegada"
docker exec app sh -c "rm -f ${TRAEFIK_DIR}/.write_test_* 2>/dev/null || true"

# 4. Confirmar el propietario del directorio
DIR_OWNER=$(stat -c '%u' "$TRAEFIK_DIR" 2>/dev/null || echo "unknown")
echo "[OWNER] Propietario del directorio: UID=$DIR_OWNER"
if [ "$DIR_OWNER" = "0" ]; then
  echo "  El directorio es de root"
  if [ -n "$APP_UID" ] && [ "$APP_UID" != "no_access" ] && [ "$APP_UID" != "0" ]; then
    echo "  La app corre como UID=$APP_UID — PROBLEMA CONFIRMADO"
  fi
fi
```

## Solución manual
```bash
# OPCIÓN A: Cambiar propietario del directorio al UID del contenedor (RECOMENDADA)

# Paso 1: Obtener el UID del contenedor de la app
APP_UID=$(docker exec app id -u 2>/dev/null || echo "1000")
APP_GID=$(docker exec app id -g 2>/dev/null || echo "1000")
echo "UID de la app: $APP_UID, GID: $APP_GID"

# Paso 2: Cambiar propietario del directorio
chown "${APP_UID}:${APP_GID}" /opt/traefik-dynamic/
# NOTA: NO usar chown recursivo (-R) si el directorio ya tiene archivos YAML
# que Traefik está leyendo — sólo cambiar el directorio en sí

# Paso 3: Verificar permisos
ls -la /opt/traefik-dynamic/
stat /opt/traefik-dynamic/ | grep -E "Uid|Gid"

# Paso 4: Test de escritura
docker exec app sh -c "touch /opt/traefik-dynamic/.write_test && echo OK && rm /opt/traefik-dynamic/.write_test"

# -----------------------------------------------------------------------
# OPCIÓN B: chmod 775 con grupo compartido (si múltiples contenedores escriben)

# Crear un grupo compartido (si no existe) y asignar el directorio
GROUP_ID=$(docker exec app id -g 2>/dev/null || echo "1000")
chown root:"${GROUP_ID}" /opt/traefik-dynamic/
chmod 775 /opt/traefik-dynamic/
# Los archivos existentes heredan el nuevo grupo:
chown -R root:"${GROUP_ID}" /opt/traefik-dynamic/*.yml 2>/dev/null || true
chmod 664 /opt/traefik-dynamic/*.yml 2>/dev/null || true

# -----------------------------------------------------------------------
# OPCIÓN C (TEMPORAL SÓLO): chmod 777 del directorio específico
# USAR SÓLO EN EMERGENCIA — ver "Auto-remediation prohibido"
# chmod 777 /opt/traefik-dynamic/
# PELIGRO: mundo-escribible, cualquier proceso del host puede modificar la configuración de Traefik

# Paso 5: Verificar que los YAMLs existentes son legibles por Traefik
docker compose -f /opt/deploy/docker-compose.yml logs --tail=10 traefik 2>&1 | grep -i "error\|warning" | tail -5

# Paso 6: Verificar que la app puede ahora crear la ruta de un inquilino
# (ej. disparar el proceso de provisioning para un inquilino pendiente)
```

## Fix permanente
El script de bootstrap del servidor (`setup.sh` o equivalente) debe crear el directorio `/opt/traefik-dynamic/` con el propietario correcto desde el inicio:

```bash
# En el script de bootstrap del servidor
APP_UID=1000  # ajustar al UID del usuario no-root del contenedor
APP_GID=1000

mkdir -p /opt/traefik-dynamic
chown "${APP_UID}:${APP_GID}" /opt/traefik-dynamic
chmod 755 /opt/traefik-dynamic

# Crear el archivo de middleware desde el inicio
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
chown "${APP_UID}:${APP_GID}" /opt/traefik-dynamic/tenant-forwardauth-middleware.yml
```

Adicionalmente, el proceso de arranque de la app debe verificar en startup que puede escribir en `/opt/traefik-dynamic/` y fallar rápido (fast-fail) si no puede:
```python
# En app startup
import os
TRAEFIK_DIR = "/opt/traefik-dynamic"
if not os.access(TRAEFIK_DIR, os.W_OK):
    raise RuntimeError(
        f"Cannot write to {TRAEFIK_DIR}. "
        f"Fix permissions: chown {os.getuid()}:{os.getgid()} {TRAEFIK_DIR}"
    )
```

## Señales para detección automática
- Log pattern: `"Permission denied.*traefik-dynamic"` o `"PermissionError.*traefik-dynamic"` en logs de `app` o `hg_scheduler`.
- Startup check: la app verifica `os.access("/opt/traefik-dynamic", os.W_OK)` al arrancar.
- Alerta de provisioning fallido: si un nuevo inquilino no obtiene su ruta en Traefik en los 30 segundos siguientes al provisioning, verificar permisos del directorio.
- Verificación periódica del scheduler: ejecutar test de escritura en `/opt/traefik-dynamic/` cada 5 minutos.

## Auto-remediation permitido
El sistema puede intentar corregir los permisos del directorio si detecta el error:
```bash
chown $(id -u):$(id -g) /opt/traefik-dynamic/
```
(acción: `fix_traefik_dynamic_dir_permissions`)
Esta acción es segura si el proceso que la ejecuta tiene privilegios suficientes para `chown` (ej. si el scheduler tiene `sudo` para esta operación específica, o si corre con un entrypoint que ejecuta el chown como root antes de bajar privilegios).

## Auto-remediation prohibido
- `chmod 777 /opt/` o cualquier directorio padre de `traefik-dynamic` — expone toda la configuración del servidor a escritura mundial.
- Montar `/opt/traefik-dynamic/` como `world-writable` permanentemente en `docker-compose.yml` — cualquier contenedor comprometido podría modificar la configuración de Traefik e inyectar rutas arbitrarias.
- Correr el contenedor `app` o `hg_scheduler` como root para evitar el problema — esto viola el principio de mínimo privilegio y amplía la superficie de ataque.

## Dashboard esperado
- Badge **CRITICAL** en el panel de administración: "Traefik config dir not writable".
- Alerta inmediata al iniciar la app si el check de escritura falla.
- Los jobs de provisioning muestran estado `failed` con error `traefik_config_write_denied`.
- Panel de infraestructura: indicador "Traefik Dynamic Dir: NOT writable" en rojo.

## RAG usage
Cuando el administrador reporte "no se pueden crear nuevos inquilinos", "error al provisionar", o cuando los logs muestren `PermissionError` referenciando `/opt/traefik-dynamic/`, este runbook es el correcto. La IA debe verificar el propietario del directorio en el host y el UID del contenedor de la app. El fix es `chown` en el host con el UID correcto. La IA debe insistir en NO usar `chmod 777` en directorios padre y en NO correr los contenedores como root.

## Tests/Chaos
```bash
#!/bin/bash
# chaos/test_traefik_dynamic_dir_rw_denied.sh
# Simula el error de permisos y verifica detección + recuperación

set -euo pipefail

TRAEFIK_DIR="/opt/traefik-dynamic"
APP_UID=$(docker exec app id -u 2>/dev/null || echo "1000")
APP_GID=$(docker exec app id -g 2>/dev/null || echo "1000")
CURRENT_OWNER=$(stat -c '%u:%g' "$TRAEFIK_DIR")

echo "[CHAOS] Cambiar propietario de $TRAEFIK_DIR a root:root"
chown root:root "$TRAEFIK_DIR"
chmod 755 "$TRAEFIK_DIR"

echo "[DETECT] Test de escritura desde contenedor app (debe fallar):"
docker exec app sh -c "touch ${TRAEFIK_DIR}/.chaos_test 2>&1" \
  && echo "[WARN] Escritura exitosa inesperadamente — ¿el contenedor corre como root?" \
  || echo "[OK] Escritura denegada correctamente"

echo "[DETECT] Intentar crear una ruta de inquilino via API:"
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "http://localhost:8000/admin/tenants/1/regenerate-route" \
  -H "Authorization: Bearer $ADMIN_TOKEN" 2>/dev/null || echo "000")
echo "  HTTP: $RESPONSE (esperado: 500 o 503, no 200)"

echo "[DETECT] Verificar error en logs:"
docker compose -f /opt/deploy/docker-compose.yml logs --since=30s app 2>&1 \
  | grep -i "permission\|errno 13\|traefik-dynamic" | head -5

echo "[RECOVER] Restaurar propietario original ($CURRENT_OWNER)"
chown "$CURRENT_OWNER" "$TRAEFIK_DIR"

echo "[VERIFY] Escritura restaurada:"
docker exec app sh -c "touch ${TRAEFIK_DIR}/.recovery_test && echo OK && rm ${TRAEFIK_DIR}/.recovery_test" 2>/dev/null \
  || echo "[FAIL] Escritura aún denegada — verificar permisos"

echo "[VERIFY] Permisos restaurados:"
stat "$TRAEFIK_DIR" | grep -E "Uid|Gid|Access"
```
