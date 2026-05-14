---
incident_id: WELCOME_TO_NGINX_EMPTY_SITE
incident_type: content
severity: high
status: confirmed
validated: true
auto_repair_allowed: true
safe_actions:
  - recreate_static_nginx_container_with_mount
forbidden_actions:
  - delete_client_files
  - disable_nginx_default_page_check
  - auto_update_dns
signatures:
  - "Welcome to nginx!"
  - "If you see this page, the nginx web server is successfully installed"
  - "HTTP 200 with nginx default body"
  - "Mounts: []"
---

# WELCOME_TO_NGINX_EMPTY_SITE

## Síntoma
El subdominio del inquilino (`mi-academia.hostingguard.lat`) devuelve HTTP 200 pero muestra la página por defecto de nginx: "Welcome to nginx! If you see this page, the nginx web server is successfully installed and working." El sitio del inquilino no aparece. El dashboard de salud puede mostrar el sitio como "healthy" (falso positivo por el HTTP 200).

## Impacto
- El sitio del inquilino no muestra contenido real — el usuario ve la página default de nginx.
- El contenido del sitio (subido via ZIP o manualmente) se ha perdido porque no tenía persistencia.
- El dashboard puede reportar estado "healthy" erróneamente basándose solo en el código HTTP 200.
- El inquilino experimenta pérdida total del sitio, aunque el enrutamiento funcione correctamente.

## Evidencia
```bash
# Confirmar el contenido de la página (no sólo el código HTTP)
curl -sf https://mi-academia.hostingguard.lat | grep -i "welcome to nginx\|nginx web server"

# Inspeccionar los mounts del contenedor nginx
docker inspect mi-academia --format='Mounts: {{json .Mounts}}'
# Salida esperada del problema: Mounts: []

# Ver el contenido del filesystem del contenedor
docker exec mi-academia ls -la /usr/share/nginx/html/ 2>/dev/null
# Si sólo hay index.html y 50x.html por defecto: PROBLEMA CONFIRMADO

# Verificar si los archivos del cliente existen en el host
ls -la /opt/clients/mi-academia/ 2>/dev/null || echo "DIRECTORIO NO EXISTE en host"

# Ver el historial de recreaciones del contenedor
docker inspect mi-academia --format='Created={{.Created}} RestartCount={{.RestartCount}}'
```

## Causa raíz
El contenedor nginx del inquilino fue creado sin bind mount hacia `/opt/clients/{container_name}/` en el host. Los archivos del sitio (subidos via ZIP import u otro método) fueron copiados dentro del sistema de archivos temporal (writable layer) del contenedor. Cuando el contenedor fue recreado (por reinicio manual, actualización, fallo de health check, o reinicio del Docker daemon), la writable layer fue destruida y el contenedor arrancó desde la imagen base de nginx, que incluye la página por defecto. La presencia de HTTP 200 hace que los health checks basados únicamente en código de respuesta no detecten el problema.

## Diagnósticos equivocados
- **"El sitio funciona porque devuelve 200"** — HTTP 200 no garantiza que el contenido sea el correcto. La página de nginx por defecto también devuelve 200. El health check debe verificar el cuerpo de la respuesta.
- **"El inquilino borró su contenido"** — Es poco probable. El contenido no desapareció voluntariamente — se perdió al recrear el contenedor sin mount persistente.
- **"El problema es el DNS"** — DNS resuelve correctamente. La ruta funciona. El problema es el contenido servido por nginx.
- **"Hay que hacer un nuevo ZIP import"** — El ZIP import también fallará si el contenedor se recrea sin mount, ya que el contenido se perderá nuevamente. Primero hay que corregir el mount.
- **"El certificado SSL es el problema"** — El 200 y la página de nginx indican que HTTPS funciona correctamente. El problema es el contenido, no el TLS.

## Diagnóstico rápido
```bash
TENANT="mi-academia"  # ajustar

echo "=== Diagnóstico WELCOME_TO_NGINX para $TENANT ==="

# 1. Verificar el contenido de la respuesta
echo "[CONTENT] Cuerpo de la respuesta:"
curl -sf "https://${TENANT}.hostingguard.lat" 2>/dev/null | head -10

# 2. Detectar página de nginx por defecto
if curl -sf "https://${TENANT}.hostingguard.lat" 2>/dev/null | grep -qi "welcome to nginx"; then
  echo "[PROBLEM] Página por defecto de nginx detectada"
else
  echo "[OK] La respuesta no parece ser la página por defecto de nginx"
fi

# 3. Verificar mounts del contenedor
MOUNTS=$(docker inspect "${TENANT}" --format='{{json .Mounts}}' 2>/dev/null)
echo "[MOUNTS] Mounts: $MOUNTS"
if [ "$MOUNTS" = "[]" ] || [ "$MOUNTS" = "null" ]; then
  echo "[PROBLEM] Contenedor sin mounts persistentes"
fi

# 4. Verificar archivos en el host
echo "[HOST] Archivos en /opt/clients/${TENANT}/:"
ls -la "/opt/clients/${TENANT}/" 2>/dev/null || echo "  DIRECTORIO NO EXISTE"

# 5. Verificar archivos dentro del contenedor
echo "[CONTAINER] Archivos en /usr/share/nginx/html/:"
docker exec "${TENANT}" ls -la /usr/share/nginx/html/ 2>/dev/null || echo "  No se puede acceder al contenedor"
```

## Solución manual
```bash
TENANT="mi-academia"  # ajustar
CONTAINER_NAME="${TENANT}"

# PASO 1: Confirmar que los archivos del cliente existen en el host
echo "[CHECK] Archivos del cliente en el host:"
ls -la "/opt/clients/${TENANT}/"

if [ ! -f "/opt/clients/${TENANT}/index.html" ]; then
  echo "[ERROR] No existe /opt/clients/${TENANT}/index.html"
  echo "  Opciones:"
  echo "  A) El cliente debe re-subir su sitio via ZIP import"
  echo "  B) Si hay backup, restaurar desde /opt/backups/"
  exit 1
fi

echo "[OK] Archivos encontrados en el host"

# PASO 2: Obtener la configuración actual del contenedor (para recrear igual)
IMAGE=$(docker inspect "${CONTAINER_NAME}" --format='{{.Config.Image}}' 2>/dev/null)
NETWORK=$(docker inspect "${CONTAINER_NAME}" --format='{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}' 2>/dev/null)
echo "  Image: $IMAGE"
echo "  Network: $NETWORK"

# PASO 3: Detener y eliminar el contenedor actual (SIN perder datos del host)
echo "[STOP] Deteniendo contenedor actual..."
docker stop "${CONTAINER_NAME}"
docker rm "${CONTAINER_NAME}"

# PASO 4: Recrear el contenedor CON bind mount persistente
echo "[CREATE] Recreando contenedor con mount persistente..."
docker run -d \
  --name "${CONTAINER_NAME}" \
  --network "${NETWORK:-hg_network}" \
  --restart unless-stopped \
  -v "/opt/clients/${TENANT}:/usr/share/nginx/html:ro" \
  "${IMAGE:-nginx:alpine}"

# PASO 5: Verificar que el contenedor arrancó con el mount correcto
echo "[VERIFY] Mounts del nuevo contenedor:"
docker inspect "${CONTAINER_NAME}" --format='{{json .Mounts}}'
# Esperado: [{"Type":"bind","Source":"/opt/clients/mi-academia","Destination":"/usr/share/nginx/html",...}]

# PASO 6: Verificar que el contenido correcto se sirve
sleep 2
echo "[VERIFY] Contenido de la respuesta:"
curl -sf "https://${TENANT}.hostingguard.lat" | head -5

if curl -sf "https://${TENANT}.hostingguard.lat" | grep -qi "welcome to nginx"; then
  echo "[PROBLEM] Aún sirve nginx default — verificar que index.html existe en /opt/clients/${TENANT}/"
else
  echo "[OK] El contenido ya no es la página por defecto de nginx"
fi
```

## Fix permanente
El proceso de creación de contenedores nginx estáticos (`create_static_nginx_container` o equivalente) debe siempre incluir el bind mount `-v /opt/clients/{container_name}:/usr/share/nginx/html:ro`. Este parámetro no debe ser opcional. Antes de crear el contenedor, el proceso debe verificar que el directorio de destino existe en el host y crear un `index.html` placeholder si está vacío, para que el contenedor arranque con contenido.

El health check `router_health_guard.py` debe verificar el cuerpo de la respuesta HTTP, no sólo el código de estado, buscando la presencia de la cadena `"Welcome to nginx"` como señal de contenido roto.

## Señales para detección automática
- Body check: respuesta HTTP contiene `"Welcome to nginx"` para un inquilino activo.
- Mount check: `docker inspect --format='{{json .Mounts}}' {container}` retorna `[]` para contenedor de tipo `static_nginx`.
- Archivo check: `/opt/clients/{container_name}/index.html` no existe en el host.
- La función `check_static_container_mounts()` en `router_health_guard.py` detecta esta condición.

## Auto-remediation permitido
- Recrear el contenedor nginx con el bind mount correcto si se cumplen todas las condiciones:
  1. El inquilino está activo en la base de datos.
  2. La imagen es nginx (no WordPress/MariaDB).
  3. No hay contenedor de base de datos asociado (`db_container` es null).
  4. El archivo `/opt/clients/{container_name}/index.html` existe en el host.
  (acción: `recreate_static_nginx_container_with_mount`)

## Auto-remediation prohibido
- Eliminar los archivos de `/opt/clients/{container_name}/` en ninguna circunstancia.
- Deshabilitar el check de cuerpo de respuesta (body check) en el health monitor.
- Actualizar DNS automáticamente como parte del fix (el DNS no está relacionado con este incidente).
- Recrear el contenedor si `index.html` no existe — sin contenido disponible, recrear el contenedor sólo perpetúa el problema.

## Dashboard esperado
- Badge **HIGH** en el panel del inquilino: "Contenido roto — nginx default page".
- El estado del inquilino debe ser `content_broken`, no `healthy`, aunque el HTTP sea 200.
- Alerta activa: "Static site serving nginx default page — mount missing".
- Indicador visual: "Mounts: None" en los detalles del contenedor del inquilino.

## RAG usage
Cuando el administrador reporte "el sitio muestra Welcome to nginx" o "el cliente dice que su sitio está en blanco", este runbook es el correcto. La IA debe diferenciar entre el HTTP 200 como señal falsa de salud y el contenido real. La causa principal a verificar son los mounts del contenedor. Si `/opt/clients/{tenant}/index.html` no existe, la IA debe indicar que el cliente necesita re-subir su contenido antes de poder auto-reparar. La IA nunca debe sugerir que el problema es DNS o TLS.

## Tests/Chaos
```bash
#!/bin/bash
# chaos/test_welcome_to_nginx.sh
# Simula el contenedor sin mount y verifica que el health check lo detecta

set -euo pipefail

TENANT="${1:-mi-academia}"
IMAGE=$(docker inspect "${TENANT}" --format='{{.Config.Image}}' 2>/dev/null || echo "nginx:alpine")
NETWORK=$(docker inspect "${TENANT}" --format='{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}' 2>/dev/null || echo "hg_network")

echo "[CHAOS] Recrear contenedor SIN mount persistente"
docker stop "${TENANT}" 2>/dev/null || true
docker rm "${TENANT}" 2>/dev/null || true
docker run -d --name "${TENANT}" --network "${NETWORK}" --restart unless-stopped "${IMAGE}"
sleep 3

echo "[DETECT] Verificar página de nginx por defecto"
BODY=$(curl -sf "https://${TENANT}.hostingguard.lat" 2>/dev/null || echo "")
if echo "$BODY" | grep -qi "welcome to nginx"; then
  echo "[OK] Problema detectado: nginx default page"
else
  echo "[WARN] Página de nginx no detectada — verificar si la ruta está activa"
fi

echo "[DETECT] Verificar mounts vacíos"
MOUNTS=$(docker inspect "${TENANT}" --format='{{json .Mounts}}' 2>/dev/null)
if [ "$MOUNTS" = "[]" ]; then
  echo "[OK] Mounts vacíos detectados"
else
  echo "[INFO] Mounts: $MOUNTS"
fi

echo "[RECOVER] Recrear contenedor CON mount"
docker stop "${TENANT}" 2>/dev/null || true
docker rm "${TENANT}" 2>/dev/null || true
docker run -d \
  --name "${TENANT}" \
  --network "${NETWORK}" \
  --restart unless-stopped \
  -v "/opt/clients/${TENANT}:/usr/share/nginx/html:ro" \
  "${IMAGE}"
sleep 3

echo "[VERIFY] Contenido restaurado:"
curl -sf "https://${TENANT}.hostingguard.lat" | head -3
MOUNTS=$(docker inspect "${TENANT}" --format='{{json .Mounts}}' 2>/dev/null)
echo "[VERIFY] Mounts: $MOUNTS"
```
