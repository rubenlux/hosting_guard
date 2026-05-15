---
incident_id: TENANT_NGINX_403_EMPTY_OR_MISSING_INDEX
incident_type: nginx_403_empty_index
severity: high
status: confirmed
validated: true
auto_repair_allowed: false
safe_actions:
  - create_placeholder_index_for_empty_static_site
  - validate_static_index_exists
  - mark_site_pending_content
  - recreate_static_nginx_container_with_mount
forbidden_actions:
  - mark_healthy_on_container_running_only
  - chmod_777_opt_clients
  - delete_client_files
  - bypass_forwardauth
signatures:
  - "HTTP/2 403"
  - "403 Forbidden"
  - "NO index.html"
  - "/usr/share/nginx/html vacío"
  - "tenant empty content"
  - "nginx directory index forbidden"
  - "nginx_403_empty_index"
  - "empty static site"
  - "nginx 403 empty"
---

# TENANT_NGINX_403_EMPTY_OR_MISSING_INDEX

## Síntoma

El subdominio del tenant (`chaos-test.hostingguard.lat`) devuelve HTTP 403 Forbidden aunque el contenedor nginx está running:

```
HTTP/2 403
content-type: text/html
server: nginx/1.x.x

<html>
<head><title>403 Forbidden</title></head>
<body>
<center><h1>403 Forbidden</h1></center>
<hr><center>nginx</center>
</body>
</html>
```

El contenedor está running, la ruta Traefik existe, pero `/usr/share/nginx/html` está vacío — sin `index.html`. nginx retorna 403 porque `autoindex` está desactivado por defecto.

## Diferencia crítica: 403 nginx vacío vs 403 ForwardAuth

| Señal | nginx vacío | ForwardAuth |
|---|---|---|
| Body | `<center>nginx</center>` | JSON o redirect |
| Content-Type | `text/html` | `application/json` o `text/html` con redirect |
| Estado del sitio | Nunca tuvo contenido | Tiene contenido, necesita auth |
| Acción correcta | Crear placeholder / subir contenido | Ninguna — comportamiento esperado |

Un 403 de ForwardAuth es **healthy**. Un 403 de nginx vacío es **unhealthy**.

## Impacto

- El tenant queda activo en la DB pero inutilizable desde el primer momento.
- El Router Health Guard acepta 403 como válido (diseñado para ForwardAuth) — **falso negativo en health check**.
- El usuario recibe un sitio que nunca funcionó, sin feedback.
- El dashboard no muestra incidente porque el health check no diferenciaba los dos tipos de 403.

## Evidencia

```bash
SUBDOMAIN="chaos-test"

# Confirmar 403 y que el body es el de nginx (no ForwardAuth)
curl -sv "https://${SUBDOMAIN}.hostingguard.lat/" 2>&1 | grep -E "< HTTP|403|nginx|location"

# Inspeccionar el directorio del contenido
docker exec "${SUBDOMAIN}" ls -la /usr/share/nginx/html/
# → total 0 (o solo "." y "..")

# Verificar en el host
ls -la "/opt/clients/${SUBDOMAIN}/"
# → directorio vacío — sin index.html

# Confirmar diferencia con ForwardAuth (ForwardAuth devuelve JSON o redirect)
curl -s "https://${SUBDOMAIN}.hostingguard.lat/" | python3 -c "import sys; body=sys.stdin.read(); print('NGINX_EMPTY' if 'nginx' in body.lower() and '403' in body else 'OTHER')"
```

## Causa raíz

Al crear un tenant estático (`POST /hosting/create`), el flujo:
1. Crea `/opt/clients/{container_name}/` con `os.makedirs()`
2. Arranca el contenedor con `-v /opt/clients/{container}/:/usr/share/nginx/html:ro`
3. Marca el hosting como `active` en la DB

**El problema**: entre el paso 1 y 2, no se crea ningún `index.html`. nginx sirve el directorio vacío y retorna 403. El hosting queda `active` sin contenido servible.

## Diagnósticos equivocados

### ❌ "El tenant tiene contenido pero nginx no lo encuentra"
**Por qué parece posible:** nginx retorna 403, lo que parece un problema de permisos.
**Por qué es incorrecto:** El 403 de nginx en directorio vacío no es un error de permisos — es que no hay nada que servir. `ls /usr/share/nginx/html` muestra directorio vacío.

### ❌ "Es el ForwardAuth bloqueando el acceso"
**Por qué parece posible:** ForwardAuth también retorna 403.
**Por qué es incorrecto:** ForwardAuth retorna 403 con body JSON o redirect. nginx vacío retorna 403 con `<center>nginx</center>` en el body. Son distinguibles por el cuerpo de la respuesta.

### ❌ "El contenedor no tiene los permisos correctos"
**Por qué parece posible:** 403 = Forbidden.
**Por qué es incorrecto:** El contenedor tiene el mount correcto. El problema es que el directorio montado está vacío, no que los permisos sean incorrectos.

### ❌ "Hay que cambiar los permisos de /opt/clients"
**Por qué es incorrecto y peligroso:** `chmod 777 /opt/clients` expone todos los archivos de todos los clientes. Prohibido explícitamente.

## Diagnóstico rápido

```bash
TENANT="${1:-chaos-test}"

echo "=== Diagnóstico TENANT_NGINX_403 para $TENANT ==="

# 1. Código HTTP
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "https://${TENANT}.hostingguard.lat/")
echo "[HTTP] Código: $STATUS"

# 2. Si es 403, determinar tipo
if [ "$STATUS" = "403" ]; then
  BODY=$(curl -s "https://${TENANT}.hostingguard.lat/")
  if echo "$BODY" | grep -qi "nginx"; then
    echo "[TYPE] 403 de nginx (directorio vacío) — INCIDENTE"
  else
    echo "[TYPE] 403 de ForwardAuth o backend — comportamiento esperado"
  fi
fi

# 3. Estado del contenedor
docker inspect "${TENANT}" --format='Estado: {{.State.Status}}' 2>/dev/null

# 4. Contenido del directorio
echo "[DIR] Archivos en /opt/clients/${TENANT}/:"
ls -la "/opt/clients/${TENANT}/" 2>/dev/null || echo "  Directorio no existe"

echo "[CONTAINER] Archivos en /usr/share/nginx/html/ del contenedor:"
docker exec "${TENANT}" ls -la /usr/share/nginx/html/ 2>/dev/null || echo "  No accesible"
```

## Solución manual

### Opción A — Crear placeholder (recomendado si el tenant acaba de ser creado)

```bash
TENANT="chaos-test"
cat > "/opt/clients/${TENANT}/index.html" << 'EOF'
<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><title>Sitio en configuración</title></head>
<body>
<h1>Sitio en configuración</h1>
<p>Este sitio está siendo configurado. Sube tu contenido desde el panel.</p>
</body>
</html>
EOF

# Verificar que nginx ahora sirve el placeholder
curl -s -o /dev/null -w "%{http_code}" "https://${TENANT}.hostingguard.lat/"
# → 200
```

### Opción B — El tenant sube su contenido

Instruir al tenant a usar el ZIP import o el deploy desde el panel para subir `index.html`.

## Fix permanente

El endpoint `POST /hosting/create` debe crear un `index.html` placeholder antes de arrancar el contenedor. Así el sitio arranca en 200 (placeholder) en lugar de 403 (vacío).

El Router Health Guard debe diferenciar 403 de nginx vacío (body contiene `nginx` y `403`) de 403 de ForwardAuth (body diferente). Solo el primer caso es `unhealthy`.

## Provisioning gate

Antes de marcar el hosting como `active`:
1. Verificar que `/opt/clients/{container_name}/index.html` existe.
2. Si no existe, crear placeholder.
3. Solo entonces arrancar el contenedor.

## Señales para detección automática

- `status_code == 403` AND body contiene `nginx` AND body contiene `Forbidden` → nginx vacío
- `docker exec {container} ls /usr/share/nginx/html` retorna directorio vacío
- `/opt/clients/{container_name}/index.html` no existe en el host

## Auto-remediation prohibido

- `mark_healthy_on_container_running_only` — el contenedor running no garantiza contenido servible.
- `chmod_777_opt_clients` — expone archivos de todos los clientes.
- `delete_client_files` — nunca borrar archivos de clientes.
- `bypass_forwardauth` — el 403 de nginx no está relacionado con ForwardAuth.

## Dashboard esperado

- Badge **HIGH** en el tenant: "Sitio sin contenido — nginx retorna 403".
- Estado del tenant: `pending_content`, no `healthy`.
- Incidente activo en Security Center: `nginx_403_empty_index`.
- Acción recomendada en UI: "Sube tu contenido o activa el placeholder".

## RAG usage

Cuando el operador reporte "el sitio devuelve 403", "recién creé el tenant y ya da error", "el contenedor está running pero el sitio no carga" → verificar si el body del 403 contiene "nginx". Si sí, este runbook. Si el body es JSON o redirect, es ForwardAuth comportamiento esperado. La IA nunca debe marcar un 403-nginx-vacío como healthy.

## Tests/Chaos

```bash
# Verificar el fix del provisioning gate:
# 1. Crear nuevo tenant via API
# 2. Inmediatamente verificar que /opt/clients/{name}/index.html existe
# 3. Verificar que el site retorna 200, no 403

# Simular el problema (en tenant descartable):
docker exec chaos-test rm /usr/share/nginx/html/index.html
curl -s -o /dev/null -w "%{http_code}" https://chaos-test.hostingguard.lat/
# → 403

# Restaurar con placeholder:
echo '<h1>Placeholder</h1>' > /opt/clients/chaos-test/index.html
curl -s -o /dev/null -w "%{http_code}" https://chaos-test.hostingguard.lat/
# → 200
```
