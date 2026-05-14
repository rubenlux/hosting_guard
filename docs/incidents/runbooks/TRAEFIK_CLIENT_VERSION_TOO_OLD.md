---
incident_id: TRAEFIK_CLIENT_VERSION_TOO_OLD
incident_type: infrastructure
severity: high
status: confirmed
validated: true
auto_repair_allowed: false
safe_actions:
  - set_docker_api_version_env
  - remove_docker_provider_from_traefik_config
forbidden_actions:
  - auto_upgrade_docker_on_production
signatures:
  - "client version 1.24 is too old"
  - "client version 1.XX is too old. Minimum version required is"
  - "the client version is too old"
  - "Error response from daemon: client version"
---

# TRAEFIK_CLIENT_VERSION_TOO_OLD

## Síntoma
Traefik produce en sus logs el mensaje exacto `"client version 1.24 is too old. Minimum version required is X.XX"` (o variante con número diferente). Este mensaje aparece al inicio del contenedor Traefik o de forma recurrente en los logs. Puede o no ir acompañado de reinicios del contenedor, dependiendo de si el error es fatal o si Traefik continúa con providers parciales.

## Impacto
- Error de negociación de versión entre el cliente Go de Traefik y el Docker Engine del host.
- Si Traefik falla al inicializar el Docker provider, pierde todas las rutas definidas vía etiquetas Docker.
- Si Traefik continúa arrancando (error no-fatal), el Docker provider queda silenciosamente desactivado sin que el operador lo note.
- Este error es el síntoma directo que lleva al incidente `TRAEFIK_DOCKER_PROVIDER_UNHEALTHY`.

## Evidencia
```bash
# Capturar el mensaje exacto de error
docker compose -f /opt/deploy/docker-compose.yml logs traefik 2>&1 | grep -i "client version\|too old\|minimum version" | tail -10

# Ver la versión de API del Docker Engine del host
docker version --format '{{.Server.APIVersion}}'

# Ver la versión de Traefik (para cruzar con su changelog de versión mínima requerida)
docker inspect traefik --format='{{.Config.Image}}'

# Verificar si existe la variable DOCKER_API_VERSION en el entorno del contenedor Traefik
docker inspect traefik --format='{{range .Config.Env}}{{println .}}{{end}}' | grep -i docker_api
```
Salida esperada del error en logs:
```
time="2024-01-15T10:23:45Z" level=error msg="provider docker: ...
Error response from daemon: client version 1.24 is too old.
Minimum version required is 1.41."
```

## Causa raíz
El cliente Docker integrado en Traefik (escrito en Go, basado en `moby/moby`) intenta negociar la versión de API con el Docker Engine del host. Traefik moderno requiere una versión mínima de API (ej. 1.41+) que no está disponible en instalaciones antiguas de Docker Engine. El host de producción tenía Docker Engine con API version 1.24, muy por debajo del mínimo. La variable de entorno `DOCKER_API_VERSION` puede forzar una versión específica, pero si la versión forzada es inferior al mínimo del cliente Go, el error persiste. La solución correcta no es forzar una versión de API antigua — es eliminar el Docker provider de Traefik.

## Diagnósticos equivocados
- **"Hay que bajar la versión de Traefik"** — Versiones antiguas de Traefik tienen vulnerabilidades conocidas. Además, el problema de fondo (Docker Engine desactualizado) seguiría existiendo y reaparecería.
- **"Con DOCKER_API_VERSION=1.24 se soluciona"** — Forzar `DOCKER_API_VERSION=1.24` para que coincida con el Engine hace que el cliente Go acepte la conexión, pero si el mínimo requerido por el cliente es mayor, el error persiste. Y aunque funcionara, estarías usando una API deprecada.
- **"Reiniciar el Docker Engine arregla la negociación"** — No. La versión del API del Engine es fija según la versión de Docker instalada; un reinicio no cambia la versión.
- **"El problema es TLS o el certificado del socket"** — El error `"client version too old"` es explícitamente de versión de protocolo, no de TLS. Si fuera TLS, el error sería `"certificate"` o `"TLS handshake"`.

## Diagnóstico rápido
```bash
# 1. Confirmar el error exacto
docker compose -f /opt/deploy/docker-compose.yml logs --tail=50 traefik 2>&1 | grep -E "too old|minimum version|client version"

# 2. Ver la versión de API del Docker Engine
docker version --format 'Client API: {{.Client.APIVersion}}\nServer API: {{.Server.APIVersion}}'

# 3. Ver si el contenedor de Traefik tiene DOCKER_API_VERSION definida
docker inspect traefik --format='{{range .Config.Env}}{{if contains . "DOCKER"}}{{println .}}{{end}}{{end}}' 2>/dev/null \
  || docker inspect traefik --format='{{range .Config.Env}}{{println .}}{{end}}' | grep DOCKER

# 4. Verificar si hay Docker provider en la config de Traefik
cat /opt/deploy/traefik/traefik.yml | grep -A5 "docker"

# 5. Confirmar el número de reinicios del contenedor Traefik
docker inspect traefik --format='RestartCount={{.RestartCount}}'
```

## Solución manual
```bash
# OPCIÓN A: Solución temporal — forzar versión de API compatible (sólo si la versión es suficiente)
# Agregar variable de entorno al servicio traefik en docker-compose.yml:
# environment:
#   - DOCKER_API_VERSION=1.41   # ajustar al valor mínimo aceptado por esta versión de Traefik
# Luego recrear el contenedor:
docker compose -f /opt/deploy/docker-compose.yml up -d --no-deps traefik
# Verificar que el error desapareció:
docker compose -f /opt/deploy/docker-compose.yml logs --tail=20 traefik | grep -i "too old\|error"

# OPCIÓN B: Solución definitiva — eliminar Docker provider (RECOMENDADA)
# Ver runbook TRAEFIK_DOCKER_PROVIDER_UNHEALTHY.md para los pasos completos.
# Resumen:
cp /opt/deploy/traefik/traefik.yml /opt/deploy/traefik/traefik.yml.bak.$(date +%Y%m%d_%H%M%S)
# Editar traefik.yml y eliminar el bloque docker: bajo providers:
nano /opt/deploy/traefik/traefik.yml
# Reiniciar Traefik
docker compose -f /opt/deploy/docker-compose.yml up -d --no-deps traefik
# Verificar limpieza total de errores
docker compose -f /opt/deploy/docker-compose.yml logs --tail=30 traefik
```

## Fix permanente
Eliminar el bloque `docker:` de la sección `providers:` en `traefik.yml`. Si por alguna razón el Docker provider es necesario en el futuro, actualizar Docker Engine a una versión cuya API sea compatible con el cliente Go de la versión de Traefik en uso, y documentar la combinación de versiones probada. La política estándar de HostingGuard es usar exclusivamente el file provider para evitar esta dependencia.

## Señales para detección automática
- Log pattern exacto: `"client version.*is too old"` en contenedor `traefik`
- Log pattern: `"Minimum version required is"` en contenedor `traefik`
- Scraping de logs via promtail/loki con alerta en Grafana sobre estos patrones
- Script de monitoreo: `docker compose logs --since=5m traefik 2>&1 | grep -c "too old"` > 0 dispara alerta

## Auto-remediation permitido
- Establecer la variable `DOCKER_API_VERSION` en el entorno del contenedor Traefik si hay una versión compatible disponible (acción: `set_docker_api_version_env`). Esta acción es segura porque sólo agrega una variable de entorno, no modifica la infraestructura.
- Registrar un incidente en `system_incidents` con severity `high` y notificar al administrador.

## Auto-remediation prohibido
- Actualizar automáticamente Docker Engine en el host de producción. Esta operación puede causar downtime total y debe ser ejecutada manualmente con ventana de mantenimiento.
- Reiniciar Traefik sin validar que el error desaparecerá con la misma configuración.

## Dashboard esperado
- Badge **HIGH** en el panel "Infrastructure" del dashboard de administración.
- Alerta visible en "Traefik Logs" con el mensaje exacto de versión.
- Si el Docker provider no inicializa, el contador de "Active Routes" en el panel Traefik debe mostrar un número inferior al baseline.
- El incidente debe listar el error exacto como evidencia reproducible.

## RAG usage
Este runbook es el punto de entrada cuando el administrador busca el error exacto `"client version too old"` o similar en los logs de Traefik. La IA debe reconocer este error como síntoma del problema estructural del Docker provider y redirigir al runbook `TRAEFIK_DOCKER_PROVIDER_UNHEALTHY.md` para el impacto completo y la solución definitiva. Si el administrador pregunta si puede forzar `DOCKER_API_VERSION`, la IA debe explicar que es una solución temporal y que la eliminación del Docker provider es la correcta.

## Tests/Chaos
```bash
#!/bin/bash
# chaos/test_traefik_client_version_too_old.sh
# Detecta si el error ya existe en logs sin necesidad de simularlo

set -euo pipefail

echo "[CHECK] Buscar error de versión en logs de Traefik (últimas 4 horas)"
ERRORS=$(docker compose -f /opt/deploy/docker-compose.yml logs --since=4h traefik 2>&1 | grep -c "too old\|minimum version" || true)

if [ "$ERRORS" -gt "0" ]; then
  echo "[ALERT] Se encontraron $ERRORS ocurrencias del error de versión de Docker API"
  docker compose -f /opt/deploy/docker-compose.yml logs --since=4h traefik 2>&1 | grep "too old\|minimum version"
  echo "[ACTION] Seguir runbook TRAEFIK_CLIENT_VERSION_TOO_OLD"
  exit 1
else
  echo "[OK] No se encontraron errores de versión de Docker API en las últimas 4 horas"
fi

echo "[CHECK] Versión de Docker Engine API del host"
SERVER_API=$(docker version --format '{{.Server.APIVersion}}')
echo "  Server API version: $SERVER_API"

# Comparación básica (requiere versión >= 1.41)
MAJOR=$(echo $SERVER_API | cut -d. -f1)
MINOR=$(echo $SERVER_API | cut -d. -f2)
if [ "$MAJOR" -lt "1" ] || ([ "$MAJOR" -eq "1" ] && [ "$MINOR" -lt "41" ]); then
  echo "[WARN] Docker API version $SERVER_API puede ser incompatible con Traefik moderno"
else
  echo "[OK] Docker API version $SERVER_API parece compatible"
fi
```
