---
incident_id: TRAEFIK_DOCKER_PROVIDER_UNHEALTHY
incident_type: infrastructure
severity: critical
status: confirmed
validated: true
auto_repair_allowed: false
safe_actions:
  - remove_docker_provider_from_traefik_config
forbidden_actions:
  - auto_upgrade_docker_on_production
  - auto_restart_traefik_without_config_backup
signatures:
  - "client version 1.24 is too old"
  - "provider docker: failed to list containers"
  - "the client version is too old. minimum version required is"
  - "Error initializing provider *docker.Provider"
---

# TRAEFIK_DOCKER_PROVIDER_UNHEALTHY

## Síntoma
Traefik entra en bucle de reinicios o pierde rutas que estaban definidas vía etiquetas Docker (labels). El panel de Traefik (si está habilitado) muestra el provider `docker` como unhealthy o ausente. Las rutas definidas vía file provider siguen funcionando, pero cualquier servicio cuya ruta dependía de etiquetas Docker desaparece del enrutamiento.

## Impacto
- Servicios enrutados exclusivamente via Docker labels devuelven 404 o connection refused.
- Traefik puede reiniiciarse repetidamente (CrashLoopBackOff visible en `docker compose ps`).
- El file provider permanece funcional, por lo que rutas de inquilinos definidas en `/opt/traefik-dynamic/` sobreviven.
- Riesgo de intermitencia si Traefik se reinicia mientras sirve peticiones activas.

## Evidencia
```bash
# Confirmar que Traefik está en bucle de reinicios
docker compose -f /opt/deploy/docker-compose.yml ps traefik

# Ver los últimos 100 logs de Traefik buscando el error de versión
docker compose -f /opt/deploy/docker-compose.yml logs --tail=100 traefik | grep -i "version\|provider\|docker"

# Ver el historial de reinicios
docker inspect --format='{{.RestartCount}}' traefik

# Confirmar la versión del socket Docker en el host
docker version --format '{{.Server.APIVersion}}'

# Ver qué providers están activos según la API de Traefik (si está expuesto)
curl -s http://localhost:8080/api/overview 2>/dev/null | python3 -m json.tool | grep -A5 "providers"
```
Salida esperada del error:
```
time="..." level=error msg="provider docker: ...client version 1.24 is too old. Minimum version required is 1.XX"
```

## Causa raíz
Traefik internamente usa el cliente Go de Docker para conectarse al socket `/var/run/docker.sock`. Cuando el Docker Engine del host tiene una API version antigua (ej. 1.24), el cliente Go de Traefik rechaza la negociación porque el mínimo soportado es superior. Traefik no puede inicializar el provider Docker, lanza un error no recuperable y se reinicia. Este problema es estructural: no desaparece sólo. La solución definitiva es eliminar el Docker provider de la configuración de Traefik y usar exclusivamente el file provider (YAML dinámicos en `/opt/traefik-dynamic/`).

## Diagnósticos equivocados
- **"Es un problema de red o DNS"** — Las rutas del file provider funcionan con normalidad. Si el problema fuera red, todas las rutas fallarían, no sólo las de labels Docker.
- **"Hay que actualizar Docker en producción"** — Actualizar Docker Engine en producción es una operación de mantenimiento mayor que requiere ventana programada, no es una solución rápida para un incidente activo.
- **"Traefik está caído"** — Traefik arranca y sirve peticiones del file provider. El problema es específico del Docker provider, no de Traefik en su totalidad.
- **"Los contenedores de inquilinos están caídos"** — Los contenedores están running; el problema es que Traefik no puede leer sus labels, no que los contenedores hayan fallado.
- **"Hay que cambiar la imagen de Traefik"** — Cambiar versión de Traefik no resuelve si el Docker Engine del host sigue siendo antiguo. La solución es eliminar la dependencia del Docker provider.

## Diagnóstico rápido
```bash
# 1. Confirmar versión de API del Docker Engine del host
docker version --format 'Server API: {{.Server.APIVersion}}'

# 2. Buscar el error exacto en logs de Traefik
docker compose -f /opt/deploy/docker-compose.yml logs traefik 2>&1 | grep -E "too old|minimum version|provider docker" | tail -20

# 3. Ver si Traefik se ha reiniciado más de 3 veces
docker inspect traefik --format='RestartCount={{.RestartCount}} Status={{.State.Status}}'

# 4. Confirmar que el file provider SÍ está activo
curl -sf http://localhost:8080/api/http/routers 2>/dev/null | python3 -m json.tool | grep '"provider"' | sort | uniq -c

# 5. Ver la config actual de Traefik para detectar si tiene Docker provider habilitado
grep -r "docker" /opt/deploy/traefik/ 2>/dev/null || cat /opt/deploy/traefik/traefik.yml 2>/dev/null | grep -A10 "providers"
```

## Solución manual
```bash
# PASO 1: Hacer backup de la configuración actual de Traefik
cp /opt/deploy/traefik/traefik.yml /opt/deploy/traefik/traefik.yml.bak.$(date +%Y%m%d_%H%M%S)

# PASO 2: Editar traefik.yml y eliminar el bloque del Docker provider
# El bloque a eliminar luce así:
#   docker:
#     endpoint: "unix:///var/run/docker.sock"
#     exposedByDefault: false
# Dejar únicamente el file provider:
#   file:
#     directory: /etc/traefik/dynamic
#     watch: true

# Editar manualmente:
nano /opt/deploy/traefik/traefik.yml
# O con sed (ajustar según estructura real del archivo):
# Verificar primero el bloque exacto:
cat /opt/deploy/traefik/traefik.yml

# PASO 3: Si el docker-compose.yml monta el socket Docker para Traefik, remover ese mount
# Buscar en docker-compose.yml:
grep -n "docker.sock\|/var/run/docker" /opt/deploy/docker-compose.yml

# Editar docker-compose.yml para eliminar el mount del socket si existe:
nano /opt/deploy/docker-compose.yml

# PASO 4: Verificar que todos los middlewares anteriormente definidos via labels
# ahora estén definidos en el file provider
ls -la /opt/traefik-dynamic/
cat /opt/traefik-dynamic/tenant-forwardauth-middleware.yml 2>/dev/null || echo "FALTA: crear middleware file"

# PASO 5: Reiniciar Traefik (sólo después de confirmar la config)
docker compose -f /opt/deploy/docker-compose.yml up -d --no-deps traefik

# PASO 6: Verificar que Traefik arranca limpio sin errores de Docker provider
docker compose -f /opt/deploy/docker-compose.yml logs --tail=30 traefik

# PASO 7: Confirmar que las rutas de inquilinos responden
curl -I https://mi-academia.hostingguard.lat 2>/dev/null | head -5
```

## Fix permanente
Eliminar completamente el Docker provider de la configuración estática de Traefik (`traefik.yml`) y migrar todas las definiciones de routers, servicios y middlewares al file provider dinámico en `/opt/traefik-dynamic/`. Esto desacopla Traefik del Docker socket y elimina la dependencia de versión de API de Docker. Ver runbook `FILE_PROVIDER_FORWARDAUTH_MIGRATION.md` para la migración de middlewares.

El archivo `traefik.yml` final debe tener únicamente:
```yaml
providers:
  file:
    directory: /etc/traefik/dynamic
    watch: true
```

Asegurarse de que el `docker-compose.yml` de producción ya **no** monte `/var/run/docker.sock` en el contenedor de Traefik.

## Señales para detección automática
- Log pattern: `"client version.*is too old"` en stdout/stderr del contenedor `traefik`
- Log pattern: `"provider docker.*failed"` o `"Error initializing provider *docker.Provider"`
- Métrica: `docker inspect traefik --format='{{.RestartCount}}'` > 3 en los últimos 10 minutos
- Health check: `docker inspect traefik --format='{{.State.Health.Status}}'` = `unhealthy`
- Alerta de disponibilidad: rutas definidas via file provider responden 200 pero rutas esperadas via labels retornan 404

## Auto-remediation permitido
Ninguna. Este incidente requiere modificación de configuración de Traefik y reinicio controlado del contenedor. Una auto-remediación que reinicie Traefik sin primero corregir la configuración perpetúa el bucle de reinicios.

## Auto-remediation prohibido
- Actualizar Docker Engine en producción de forma automática (puede romper otros servicios dependientes de Docker).
- Reiniciar Traefik sin hacer backup de la configuración actual y sin verificar que el file provider está correctamente configurado.
- Eliminar el bloque Docker provider sin verificar primero que todos los middlewares que dependían de Docker labels están presentes en el file provider.

## Dashboard esperado
- Badge **CRITICAL** en el panel "Infrastructure" del dashboard de administración.
- Panel "Traefik Health" muestra estado `unhealthy` o `restarting`.
- Contador de rutas activas disminuido respecto al baseline si había rutas via Docker labels.
- Alerta activa en `system_incidents` con `source_table='traefik_health'`, `severity='critical'`.

## RAG usage
Cuando el administrador reporte que "Traefik se reinicia solo", "rutas desaparecen" o "Docker provider unhealthy", este runbook debe ser el primero en consultar. La IA debe sugerir verificar la versión de la API Docker del host y comprobar si la configuración de Traefik tiene el bloque `docker:` en providers. Si el error en logs es `"client version.*is too old"`, dirigir a `TRAEFIK_CLIENT_VERSION_TOO_OLD.md` como runbook complementario. La IA no debe sugerir reiniciar Traefik como primer paso — debe primero validar la configuración.

## Tests/Chaos
```bash
#!/bin/bash
# chaos/test_traefik_docker_provider_unhealthy.sh
# Simula el incidente: activa el Docker provider con una versión incompatible y verifica detección

set -euo pipefail

echo "[CHAOS] Backup traefik.yml"
cp /opt/deploy/traefik/traefik.yml /tmp/traefik.yml.chaos_backup

echo "[CHAOS] Inyectar Docker provider en traefik.yml"
cat >> /opt/deploy/traefik/traefik.yml <<'EOF'
  docker:
    endpoint: "unix:///var/run/docker.sock"
    exposedByDefault: false
EOF

echo "[CHAOS] Reiniciar Traefik con config rota"
docker compose -f /opt/deploy/docker-compose.yml up -d --no-deps traefik
sleep 5

echo "[DETECT] Verificar error en logs"
if docker compose -f /opt/deploy/docker-compose.yml logs --tail=50 traefik 2>&1 | grep -q "too old\|provider docker"; then
  echo "[OK] Error detectado correctamente"
else
  echo "[WARN] Error no detectado en logs — revisar si la versión de Docker es compatible"
fi

echo "[RECOVER] Restaurar configuración original"
cp /tmp/traefik.yml.chaos_backup /opt/deploy/traefik/traefik.yml
docker compose -f /opt/deploy/docker-compose.yml up -d --no-deps traefik
sleep 5

echo "[VERIFY] Traefik debe estar running sin reinicios"
docker inspect traefik --format='RestartCount={{.RestartCount}} Status={{.State.Status}}'

echo "[VERIFY] Ruta de prueba responde"
curl -sf -o /dev/null -w "%{http_code}" https://mi-academia.hostingguard.lat || true
```
