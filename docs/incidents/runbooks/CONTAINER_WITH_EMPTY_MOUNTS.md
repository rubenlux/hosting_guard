---
incident_id: CONTAINER_WITH_EMPTY_MOUNTS
incident_type: infrastructure
severity: high
status: confirmed
validated: true
auto_repair_allowed: true
safe_actions:
  - recreate_static_nginx_container_with_mount
forbidden_actions:
  - chmod_777_opt_clients
  - delete_client_data_without_snapshot
signatures:
  - "\"Mounts\": []"
  - "Mounts: []"
  - "check_static_container_mounts: no mounts found"
  - "container has no persistent storage"
---

# CONTAINER_WITH_EMPTY_MOUNTS

## Síntoma
`docker inspect {container_name}` muestra `"Mounts": []`. El contenedor nginx que sirve el sitio estático de un inquilino no tiene ningún volumen ni bind mount configurado. Este es el diagnóstico estructural que causa `WELCOME_TO_NGINX_EMPTY_SITE`. El contenedor puede estar running y devolver HTTP 200 (con la página por defecto de nginx), pero cualquier contenido cargado previamente se pierde al recrear el contenedor.

## Impacto
- Todo el contenido del sitio del inquilino es **efímero**: se pierde en el próximo reinicio o recreación del contenedor.
- El inquilino puede estar viendo su sitio temporalmente si el contenedor aún no ha sido recreado desde la última carga de contenido.
- Si el contenedor se recrea (por cualquier razón), el inquilino perderá su sitio sin previo aviso.
- El riesgo aumenta con el tiempo: cuanto más tiempo pase sin detectar este estado, más probable es que el contenedor sea recreado.

## Evidencia
```bash
# Comando de diagnóstico principal
docker inspect --format='{{json .Mounts}}' mi-academia
# Salida del problema: []

# Ver detalles completos del contenedor
docker inspect mi-academia | python3 -m json.tool | grep -A10 '"Mounts"'

# Verificar si hay archivos en el host que debería estar montados
ls -la /opt/clients/mi-academia/ 2>/dev/null

# Ver el comando con el que fue creado el contenedor (HostConfig)
docker inspect mi-academia --format='{{json .HostConfig.Binds}}'
# Salida del problema: null o []

# Verificar el contenido actual dentro del contenedor
docker exec mi-academia ls -la /usr/share/nginx/html/
# Si sólo hay index.html (50 bytes, nginx default) y 50x.html: problema activo

# Verificar cuánto hace que el contenedor fue creado
docker inspect mi-academia --format='Created: {{.Created}}'
```
Salida esperada del problema:
```json
[]
```
Y en HostConfig.Binds:
```json
null
```

## Causa raíz
El contenedor fue creado sin el flag `-v /opt/clients/{container_name}:/usr/share/nginx/html:ro`. Esto puede ocurrir por:
1. El código de provisioning de contenedores tenía un bug que omitía el bind mount en contenedores de tipo `static_nginx`.
2. El contenedor fue recreado manualmente con `docker run` sin incluir el mount.
3. Un proceso automatizado (ej. health check que intenta "reparar" el contenedor) lo recreó incorrectamente.
4. El contenedor fue creado desde el `docker-compose.yml` incorrecto que no incluía el volume.

## Diagnósticos equivocados
- **"El contenedor está saludable porque está running"** — El estado `running` de Docker no verifica la integridad del contenido. Un contenedor puede estar running y sirviendo contenido incorrecto.
- **"Si HTTP devuelve 200, el sitio está bien"** — Falso positivo. La página default de nginx devuelve 200. Ver `DASHBOARD_FALSE_100_HEALTH.md`.
- **"Los archivos del inquilino se perdieron del servidor"** — Los archivos pueden seguir existiendo en `/opt/clients/{name}/` en el host. El problema es que el contenedor no los monta.
- **"Hay que darle más RAM/CPU al contenedor"** — El problema no es de recursos, es de configuración de almacenamiento.
- **"El contenedor de nginx tiene un bug"** — La imagen nginx:alpine funciona correctamente; el problema es la ausencia del mount, no la imagen.

## Diagnóstico rápido
```bash
#!/bin/bash
# Diagnóstico de todos los contenedores nginx estáticos sin mounts

echo "=== Contenedores nginx sin mounts persistentes ==="

# Obtener todos los contenedores activos con imagen nginx
docker ps --filter "ancestor=nginx" --format "{{.Names}}" | while read CONTAINER; do
  MOUNTS=$(docker inspect "$CONTAINER" --format='{{json .Mounts}}' 2>/dev/null)
  if [ "$MOUNTS" = "[]" ] || [ "$MOUNTS" = "null" ]; then
    echo "[PROBLEM] $CONTAINER: sin mounts"
    # Verificar si hay archivos en el host
    if [ -d "/opt/clients/$CONTAINER" ]; then
      FILES=$(ls /opt/clients/$CONTAINER/ | wc -l)
      echo "  Archivos en host: $FILES"
    else
      echo "  Sin directorio en host: /opt/clients/$CONTAINER"
    fi
  else
    echo "[OK] $CONTAINER: tiene mounts"
    echo "  $MOUNTS" | python3 -c "import sys,json; mounts=json.load(sys.stdin); [print(f'    {m.get(\"Source\")} -> {m.get(\"Destination\")}') for m in mounts]"
  fi
done

# Para un contenedor específico:
# CONTAINER="mi-academia"
# docker inspect --format='{{json .Mounts}}' "$CONTAINER"
```

## Solución manual
```bash
TENANT="mi-academia"  # ajustar al nombre del contenedor/inquilino

# PRECONDICIÓN 1: Verificar que el inquilino es de tipo static_nginx
# (no WordPress — WordPress usa volúmenes diferentes)
IMAGE=$(docker inspect "${TENANT}" --format='{{.Config.Image}}' 2>/dev/null)
echo "Imagen del contenedor: $IMAGE"
# Debe contener "nginx", no "wordpress" o "php"

# PRECONDICIÓN 2: Verificar que los archivos del cliente existen en el host
echo "Archivos en el host:"
ls -la "/opt/clients/${TENANT}/" 2>/dev/null

if [ ! -f "/opt/clients/${TENANT}/index.html" ]; then
  echo "[ERROR] No hay index.html en /opt/clients/${TENANT}/"
  echo "El cliente debe subir su contenido antes de continuar."
  echo "Alternativa: crear un placeholder temporal:"
  mkdir -p "/opt/clients/${TENANT}"
  cat > "/opt/clients/${TENANT}/index.html" <<'PLACEHOLDER'
<!DOCTYPE html>
<html><body><h1>Sitio en construcción</h1></body></html>
PLACEHOLDER
  echo "[INFO] Placeholder creado — el cliente deberá reemplazarlo con su contenido"
fi

# PRECONDICIÓN 3: No hay contenedor de base de datos asociado (es static, no WordPress)
DB_CONTAINER=$(docker ps --format='{{.Names}}' | grep "${TENANT}_db" 2>/dev/null || echo "")
if [ -n "$DB_CONTAINER" ]; then
  echo "[ABORT] Este contenedor tiene una base de datos asociada ($DB_CONTAINER)."
  echo "No es un sitio estático simple. Usar el proceso de WordPress para recrear."
  exit 1
fi

# OBTENER config actual del contenedor
IMAGE=$(docker inspect "${TENANT}" --format='{{.Config.Image}}' 2>/dev/null || echo "nginx:alpine")
NETWORK=$(docker inspect "${TENANT}" --format='{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}' 2>/dev/null || echo "hg_network")
ENV_VARS=$(docker inspect "${TENANT}" --format='{{range .Config.Env}}--env {{.}} {{end}}' 2>/dev/null || echo "")
LABELS=$(docker inspect "${TENANT}" --format='{{json .Config.Labels}}' 2>/dev/null || echo "{}")

echo "[INFO] Recreando contenedor:"
echo "  Image: $IMAGE"
echo "  Network: $NETWORK"
echo "  Mount: /opt/clients/${TENANT} -> /usr/share/nginx/html"

# RECREAR con bind mount
docker stop "${TENANT}"
docker rm "${TENANT}"

docker run -d \
  --name "${TENANT}" \
  --network "${NETWORK}" \
  --restart unless-stopped \
  -v "/opt/clients/${TENANT}:/usr/share/nginx/html:ro" \
  "${IMAGE}"

echo "[VERIFY] Verificando mounts del nuevo contenedor:"
MOUNTS=$(docker inspect "${TENANT}" --format='{{json .Mounts}}' 2>/dev/null)
echo "  Mounts: $MOUNTS"

if [ "$MOUNTS" = "[]" ]; then
  echo "[ERROR] El contenedor aún no tiene mounts. Revisar comando docker run."
else
  echo "[OK] Mounts configurados correctamente"
fi

echo "[VERIFY] Contenido servido:"
sleep 2
curl -sf "https://${TENANT}.hostingguard.lat" | head -5

echo "[VERIFY] Contenido del contenedor:"
docker exec "${TENANT}" ls -la /usr/share/nginx/html/
```

## Fix permanente
La función de creación de contenedores estáticos en el backend debe incluir obligatoriamente el bind mount. Agregar una verificación en el código que lance una excepción si se intenta crear un contenedor `static_nginx` sin especificar el path del bind mount en el host.

Adicionalmente, el scheduler de health check (`router_health_guard.py`) debe ejecutar periódicamente `check_static_container_mounts()` para todos los contenedores nginx activos y crear un incidente si detecta `Mounts: []`.

## Señales para detección automática
- `docker inspect --format='{{json .Mounts}}' {container}` retorna `[]` para contenedor de tipo static_nginx.
- La función `check_static_container_mounts()` en `router_health_guard.py` debe ejecutarse en cada ciclo de health check.
- Correlación: contenedor nginx con Mounts=[] + `/opt/clients/{name}/index.html` existe = reparable automáticamente.
- Correlación: contenedor nginx con Mounts=[] + `/opt/clients/{name}/` no existe = no reparable automáticamente, requiere intervención del cliente.

## Auto-remediation permitido
Recrear el contenedor con el bind mount correcto si se cumplen TODAS estas condiciones:
1. El inquilino está marcado como activo en la base de datos (`status = 'active'`).
2. La imagen del contenedor es nginx (no WordPress, PHP, etc.).
3. No existe un contenedor de base de datos asociado (`{name}_db` no está running).
4. El archivo `/opt/clients/{container_name}/index.html` existe y es legible.
(acción: `recreate_static_nginx_container_with_mount`)

## Auto-remediation prohibido
- `chmod 777 /opt/clients/` — cambiar permisos en masa expone datos de otros inquilinos.
- Eliminar o mover archivos de `/opt/clients/{name}/` sin snapshot previo.
- Recrear el contenedor si no existe `/opt/clients/{name}/index.html` — el contenedor arrancaría de nuevo con la página default de nginx.
- Recrear un contenedor WordPress como si fuera nginx estático — son arquitecturas diferentes.

## Dashboard esperado
- Badge **HIGH** en el panel del inquilino: "Storage not persistent — data at risk".
- Icono de advertencia en la columna "Storage" del listado de contenedores.
- Alerta activa: "Container {name} has no persistent mounts — content will be lost on restart".
- Panel de riesgo: listado de contenedores con Mounts=[] ordenados por antigüedad.

## RAG usage
Este runbook es el diagnóstico estructural que subyace a `WELCOME_TO_NGINX_EMPTY_SITE`. Si el administrador ya confirmó la página de nginx pero quiere entender la causa raíz, este runbook explica el problema de los mounts. La IA debe verificar las cuatro precondiciones antes de sugerir la auto-remediación: activo, nginx, sin DB, index.html existe. Si la precondición del index.html falla, la IA debe indicar que el cliente necesita re-subir su contenido.

## Tests/Chaos
```bash
#!/bin/bash
# chaos/test_empty_mounts_detection.sh
# Verifica que check_static_container_mounts detecta correctamente Mounts=[]

set -euo pipefail

TENANT="${1:-mi-academia}"

echo "=== Test: detección de Mounts=[] ==="

# Verificar estado actual
MOUNTS=$(docker inspect "${TENANT}" --format='{{json .Mounts}}' 2>/dev/null || echo "[]")
echo "Estado actual de Mounts: $MOUNTS"

# Ejecutar el health check manualmente via API
echo "[TEST] Ejecutar router health check via API:"
curl -sf -X POST "http://localhost:8000/admin/router-health/run-check" \
  -H "Authorization: Bearer $ADMIN_TOKEN" 2>/dev/null \
  | python3 -m json.tool 2>/dev/null | grep -i "mount\|empty\|${TENANT}" || echo "  (requiere ADMIN_TOKEN)"

# Verificar en DB si se creó el incidente
echo "[TEST] Buscar incidente en sistema:"
docker exec -i hg_db psql -U hguser -d hostingguard -c \
  "SELECT id, tenant_id, incident_type, severity, status, created_at
   FROM system_incidents
   WHERE source_table = 'router_health_guard'
   AND description LIKE '%${TENANT}%mounts%'
   ORDER BY created_at DESC LIMIT 5;" 2>/dev/null || echo "  (requiere acceso a DB)"
```
