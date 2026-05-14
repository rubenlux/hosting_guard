---
incident_id: FILE_PROVIDER_FORWARDAUTH_MIGRATION
incident_type: migration
severity: high
status: confirmed
validated: true
auto_repair_allowed: true
safe_actions:
  - regenerate_file_provider_forwardauth
  - migrate_all_tenant_yamls_to_file_provider
forbidden_actions:
  - delete_tenant_yamls_without_backup
  - restart_traefik_mid_migration
signatures:
  - "middleware hg-forwardauth@docker does not exist"
  - "hg-forwardauth@file: middleware not found"
  - "partial migration: mixed @docker and @file references detected"
---

# FILE_PROVIDER_FORWARDAUTH_MIGRATION

## Síntoma
Durante o después de la migración de `hg-forwardauth@docker` a `hg-forwardauth@file`, algunos o todos los inquilinos devuelven 404. Los síntomas varían según el estado de la migración:
- **Migración no iniciada**: todos los YAMLs usan `@docker`, middleware no existe → todos devuelven 404.
- **Migración parcial**: algunos YAMLs usan `@docker`, otros `@file` → sólo los que usan `@docker` devuelven 404.
- **Archivo de definición faltante, YAMLs migrados**: todos usan `@file` pero el archivo de middleware no existe → todos devuelven 404.
- **Migración completa correcta**: todos usan `@file`, archivo existe → funcionamiento normal.

## Impacto
- Impacto parcial o total en rutas de inquilinos según el estado de la migración.
- Los inquilinos cuyas rutas referencian un middleware inexistente son silenciosamente descartados por Traefik.
- Posible ruptura de la autenticación si el archivo de definición del middleware apunta a una URL incorrecta del backend.

## Evidencia
```bash
# Estado de la migración: contar referencias por tipo
echo "=== Estado de migración ==="
echo "Referencias @docker:"
grep -rl "hg-forwardauth@docker" /opt/traefik-dynamic/ 2>/dev/null | wc -l
grep -rl "hg-forwardauth@docker" /opt/traefik-dynamic/ 2>/dev/null

echo "Referencias @file:"
grep -rl "hg-forwardauth@file" /opt/traefik-dynamic/ 2>/dev/null | wc -l
grep -rl "hg-forwardauth@file" /opt/traefik-dynamic/ 2>/dev/null

echo "Archivo de definición del middleware:"
ls -la /opt/traefik-dynamic/tenant-forwardauth-middleware.yml 2>/dev/null \
  && cat /opt/traefik-dynamic/tenant-forwardauth-middleware.yml \
  || echo "NO EXISTE"

echo "Middlewares activos en Traefik:"
curl -sf http://localhost:8080/api/http/middlewares 2>/dev/null \
  | python3 -c "import sys,json; [print(m['name'], m.get('provider','?')) for m in json.load(sys.stdin)]"

echo "Errores de middleware en Traefik logs (últimos 5min):"
docker compose -f /opt/deploy/docker-compose.yml logs --since=5m traefik 2>&1 \
  | grep -i "middleware\|does not exist\|forwardauth"
```

## Causa raíz
La migración de Docker provider a file provider requiere que se cumplan tres condiciones en orden estricto:
1. El archivo `/opt/traefik-dynamic/tenant-forwardauth-middleware.yml` debe existir con la definición correcta.
2. Todos los archivos YAML de inquilinos deben referenciar `hg-forwardauth@file` (no `@docker`).
3. Traefik debe haber recargado la configuración (automático via file watcher).

Si cualquiera de estas condiciones falla o se ejecutan fuera de orden, algún subconjunto de rutas queda inaccesible. La migración parcial es el estado más peligroso porque es difícil de detectar sin revisar todos los archivos.

## Diagnósticos equivocados
- **"Ya migré los YAMLs, debe ser otro problema"** — La migración puede estar incompleta. Siempre verificar con `grep -rl` para confirmar que no quedan referencias `@docker`.
- **"El archivo de middleware existe, por qué falla"** — El archivo puede existir pero contener errores de sintaxis YAML, o apuntar a una URL incorrecta del backend (`http://app:8000/auth/verify` debe ser accesible desde Traefik en la red de Docker).
- **"Traefik no recargó el archivo"** — El file watcher de Traefik debería detectar cambios automáticamente. Si hay dudas, verificar en los logs de Traefik que cargó el nuevo archivo.
- **"Los inquilinos que funcionan prueban que la migración está bien"** — En una migración parcial, algunos inquilinos funcionan y otros no. No extrapolar.
- **"Reiniciar Traefik en medio de la migración lo soluciona"** — Reiniciar en mitad de una migración parcial puede causar un estado inconsistente si el file watcher no ha procesado todos los cambios.

## Diagnóstico rápido
```bash
# Script completo de diagnóstico de estado de migración
#!/bin/bash
echo "=== DIAGNÓSTICO DE MIGRACIÓN ForwardAuth ==="

TOTAL=$(ls /opt/traefik-dynamic/tenants-active.yml /opt/traefik-dynamic/tenant-*.yml 2>/dev/null | wc -l)
DOCKER_REFS=$(grep -rl "hg-forwardauth@docker" /opt/traefik-dynamic/ 2>/dev/null | wc -l)
FILE_REFS=$(grep -rl "hg-forwardauth@file" /opt/traefik-dynamic/ 2>/dev/null | wc -l)
MW_FILE_EXISTS=$(test -f /opt/traefik-dynamic/tenant-forwardauth-middleware.yml && echo "SI" || echo "NO")

echo "Archivos YAML de inquilinos: $TOTAL"
echo "Usan @docker: $DOCKER_REFS"
echo "Usan @file: $FILE_REFS"
echo "Archivo de definición middleware: $MW_FILE_EXISTS"

if [ "$DOCKER_REFS" -eq "0" ] && [ "$FILE_REFS" -gt "0" ] && [ "$MW_FILE_EXISTS" = "SI" ]; then
  echo "ESTADO: Migración completa y correcta"
elif [ "$DOCKER_REFS" -gt "0" ] && [ "$FILE_REFS" -eq "0" ]; then
  echo "ESTADO: Migración no iniciada — todos usan @docker"
elif [ "$DOCKER_REFS" -gt "0" ] && [ "$FILE_REFS" -gt "0" ]; then
  echo "ESTADO: MIGRACIÓN PARCIAL — estado inconsistente, acción requerida"
elif [ "$MW_FILE_EXISTS" = "NO" ]; then
  echo "ESTADO: Archivo de definición de middleware FALTANTE"
fi
```

## Solución manual
```bash
# FASE 1: Verificar el estado actual (ver Diagnóstico rápido arriba)

# FASE 2: Crear el archivo de definición del middleware (idempotente, se puede ejecutar siempre)
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
echo "[OK] Archivo de middleware creado"

# FASE 3: Esperar a que Traefik cargue el nuevo archivo
sleep 2
MW_LOADED=$(curl -sf http://localhost:8080/api/http/middlewares 2>/dev/null \
  | python3 -c "import sys,json; data=json.load(sys.stdin); print(any('hg-forwardauth' in m['name'] for m in data))" 2>/dev/null)
echo "Middleware cargado en Traefik: $MW_LOADED"

if [ "$MW_LOADED" != "True" ]; then
  echo "[ERROR] El middleware no fue cargado por Traefik. Revisar sintaxis del archivo y logs de Traefik."
  docker compose -f /opt/deploy/docker-compose.yml logs --tail=20 traefik
  exit 1
fi

# FASE 4: Migrar todos los YAMLs que aún usan @docker (con backup)
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/tmp/yaml_migration_backup_$TIMESTAMP"
mkdir -p "$BACKUP_DIR"

FILES=$(grep -rl "hg-forwardauth@docker" /opt/traefik-dynamic/ 2>/dev/null)
if [ -z "$FILES" ]; then
  echo "[OK] No hay archivos con referencias @docker"
else
  for f in $FILES; do
    cp "$f" "$BACKUP_DIR/$(basename $f)"
    sed -i 's/hg-forwardauth@docker/hg-forwardauth@file/g' "$f"
    echo "[MIGRADO] $f"
  done
  echo "[OK] Backups en: $BACKUP_DIR"
fi

# FASE 5: Verificación final
sleep 2
REMAINING=$(grep -rl "hg-forwardauth@docker" /opt/traefik-dynamic/ 2>/dev/null | wc -l)
echo "Referencias @docker restantes: $REMAINING (debe ser 0)"

echo "=== Verificación de rutas ==="
# Probar 3 inquilinos activos (ajustar subdominios según entorno)
for TENANT in mi-academia otro-cliente test-site; do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" "https://${TENANT}.hostingguard.lat" 2>/dev/null || echo "000")
  echo "  $TENANT: HTTP $STATUS (esperado: 401 o 302, NO 404)"
done
```

## Fix permanente
El proceso de provisioning de nuevos inquilinos (función `write_tenant_traefik_config` o equivalente en el backend) debe:
1. Siempre escribir `hg-forwardauth@file` en el campo `middlewares` del router del inquilino.
2. Verificar en el momento de escritura que `/opt/traefik-dynamic/tenant-forwardauth-middleware.yml` existe.
3. Si el archivo de definición no existe, crearlo antes de escribir la ruta del inquilino.

El script de bootstrap del servidor debe incluir la creación de `tenant-forwardauth-middleware.yml` como paso obligatorio.

## Señales para detección automática
- Detección de migración parcial: `grep -rl "@docker" /opt/traefik-dynamic/` retorna archivos cuando el Docker provider está desactivado.
- Verificación continua: número de routers activos en Traefik API vs número de inquilinos activos en base de datos deben coincidir.
- Log pattern: cualquier `"does not exist"` relacionado con middleware en logs de Traefik.

## Auto-remediation permitido
- Crear el archivo `tenant-forwardauth-middleware.yml` si no existe (acción: `regenerate_file_provider_forwardauth`).
- Migrar todos los YAMLs de `@docker` a `@file` con backup previo (acción: `migrate_all_tenant_yamls_to_file_provider`). La operación de `sed` es segura y reversible desde backup.

## Auto-remediation prohibido
- Eliminar YAMLs de inquilinos sin backup previo.
- Reiniciar Traefik durante la migración (entre la Fase 3 y Fase 4). El file watcher maneja la recarga automáticamente.
- Modificar el campo `address` del ForwardAuth sin validar que la nueva URL es accesible desde Traefik.

## Dashboard esperado
- Badge **HIGH** en el panel "Tenant Routes" con descripción "ForwardAuth migration incomplete".
- Lista de inquilinos afectados con estado `unavailable` (los que aún usan `@docker`).
- Panel de progreso de migración si se implementa: X de Y inquilinos migrados.
- Alerta activa hasta que `grep -rl "@docker" /opt/traefik-dynamic/` devuelva 0 resultados.

## RAG usage
Este runbook es específico para el proceso de migración y su diagnóstico. Si el administrador reporta "algunos inquilinos funcionan y otros no después de cambiar la configuración de Traefik", la IA debe ejecutar el script de diagnóstico de estado de migración para determinar si es una migración parcial. La IA debe enfatizar que la migración debe ser atómica: crear el archivo de definición primero, luego migrar los YAMLs. Si el problema ocurrió antes de la migración, redirigir a `FORWARDAUTH_MIDDLEWARE_DOCKER_MISSING.md`.

## Tests/Chaos
```bash
#!/bin/bash
# chaos/test_file_provider_migration.sh
# Simula los 4 estados de migración y verifica el comportamiento esperado

set -euo pipefail

MW_FILE="/opt/traefik-dynamic/tenant-forwardauth-middleware.yml"
TEST_YAML="/opt/traefik-dynamic/tenants-active.yml"
BACKUP_DIR="/tmp/chaos_migration_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Backup
cp "$MW_FILE" "$BACKUP_DIR/" 2>/dev/null || true
cp "$TEST_YAML" "$BACKUP_DIR/" 2>/dev/null || true

echo "=== Test 1: Migración no iniciada (todos @docker) ==="
sed -i 's/hg-forwardauth@file/hg-forwardauth@docker/g' "$TEST_YAML"
rm -f "$MW_FILE"
sleep 3
STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://mi-academia.hostingguard.lat 2>/dev/null || echo "000")
echo "  HTTP: $STATUS (esperado 404)"

echo "=== Test 2: Migración completa y correcta ==="
# Restaurar
cp "$BACKUP_DIR/$(basename $MW_FILE)" "$MW_FILE" 2>/dev/null || true
sed -i 's/hg-forwardauth@docker/hg-forwardauth@file/g' "$TEST_YAML"
sleep 3
STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://mi-academia.hostingguard.lat 2>/dev/null || echo "000")
echo "  HTTP: $STATUS (esperado 401 o 302, no 404)"

echo "=== Restaurando estado original ==="
cp "$BACKUP_DIR/$(basename $TEST_YAML)" "$TEST_YAML" 2>/dev/null || true
echo "[DONE] Estado restaurado"
```
