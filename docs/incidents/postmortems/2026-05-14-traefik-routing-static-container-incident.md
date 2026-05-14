# Postmortem — Traefik Routing Outage + Static Container Content Loss
**Fecha:** 2026-05-14  
**Severidad:** Critical (routing) + High (content loss)  
**Duración del incidente:** ~4 horas (diagnóstico iterativo)  
**Runbooks nacidos:** TRAEFIK_DOCKER_PROVIDER_UNHEALTHY, TRAEFIK_CLIENT_VERSION_TOO_OLD, FORWARDAUTH_MIDDLEWARE_DOCKER_MISSING, FILE_PROVIDER_FORWARDAUTH_MIGRATION, WELCOME_TO_NGINX_EMPTY_SITE, CONTAINER_WITH_EMPTY_MOUNTS, TRAEFIK_DYNAMIC_DIR_RW_DENIED, DASHBOARD_FALSE_100_HEALTH, ROUTER_HEALTH_INCIDENTS_DELETED_BY_SYNC

---

## Timeline

| Hora (UTC) | Evento |
|---|---|
| T+00:00 | Traefik logs muestran `client version 1.24 is too old` repetidamente |
| T+00:10 | Docker provider errores en cascada — rutas por labels dejan de funcionar |
| T+00:15 | Platform routes (file provider) siguen funcionando — se confunde con "todo ok" |
| T+00:30 | Se detecta que `hg-forwardauth@docker` no existe — Traefik rechaza rutas de tenants |
| T+00:45 | Curl a tenants devuelve 404 — admin dashboard muestra plataforma degradada |
| T+01:00 | Diagnóstico incorrecto: se asume que es un problema de DNS |
| T+01:30 | Se verifica DNS — resuelve correctamente. Se descarta DNS |
| T+01:45 | Diagnóstico incorrecto: se asume que Traefik necesita restart |
| T+02:00 | Traefik restart sin cambiar config — el error persiste |
| T+02:15 | Se identifica el problema real: Docker provider incompatible. Decisión: remover Docker provider |
| T+02:30 | Se remueven flags `--providers.docker.*` de docker-compose.yml (manualmente en servidor) |
| T+02:35 | Traefik reiniciado — ya no hay errores de Docker provider |
| T+02:40 | Nuevo problema: middleware `hg-forwardauth@docker` ya no existe (era del Docker provider) |
| T+02:50 | Se crea `/opt/traefik-dynamic/tenant-forwardauth-middleware.yml` con definición `@file` |
| T+03:00 | Se migran todos los YAMLs de tenants de `@docker` → `@file` via sed |
| T+03:10 | Se elimina `tenant-smoke-mi-test.yml` (ruta sin forwardauth — riesgo de bypass) |
| T+03:20 | Tenants responden 200 — auth funciona |
| T+03:25 | mi-academia.hostingguard.lat devuelve "Welcome to nginx!" — contenido perdido |
| T+03:30 | `docker inspect` muestra `Mounts: []` — container sin bind mount |
| T+03:45 | Se verifica que archivos existen en `/opt/clients/mi-academia/` |
| T+04:00 | Container recreado con `-v /opt/clients/mi-academia:/usr/share/nginx/html:ro` |
| T+04:05 | Sitio funciona correctamente |

---

## Impacto

- **Tenants afectados:** 4 (todos los tenants activos)
- **Duración outage routing:** ~2h 30min
- **Duración contenido perdido (mi-academia):** Indeterminado — el contenido estaba perdido desde la última recreación del container (semanas antes)
- **Usuarios afectados:** Clientes de todos los tenants durante el outage
- **Pérdida de datos:** Ninguna — archivos estaban en `/opt/clients/` (no en container)
- **Ingresos afectados:** Riesgo de churn por tiempo de inactividad

---

## Síntomas

1. Traefik logs: `client version 1.24 is too old. Minimum version required is X.XX`
2. Traefik logs: `middleware hg-forwardauth@docker does not exist`
3. Curl a tenants: HTTP 404 o conexión rechazada
4. Dashboard plataforma: degradado (rojo)
5. Dashboard tenants: incidentes de `public_route_404`
6. `mi-academia.hostingguard.lat`: HTTP 200 pero body = "Welcome to nginx!"
7. Admin dashboard: falsamente 100% healthy antes de detectar el contenido

---

## Evidencia

```bash
# Traefik logs
docker compose logs traefik | grep "too old"
# → time="..." level=error msg="client version 1.24 is too old..."

# Middleware missing
docker compose logs traefik | grep "forwardauth"
# → time="..." level=error msg="middleware hg-forwardauth@docker does not exist"

# Tenant check
curl -I https://mi-academia.hostingguard.lat
# → HTTP 404 (durante outage)

# Mounts
docker inspect user_1_mi_academia --format='{{json .Mounts}}'
# → []

# Contenido en host
ls /opt/clients/user_1_mi_academia/
# → index.html (archivos presentes)
```

---

## Causa raíz múltiple

### Causa 1 — Docker API version incompatible (RAÍZ PRINCIPAL)
El servidor de Docker en producción reportaba API version 1.24. Traefik (Go client) exige una versión mínima superior. Al iniciar, el Docker provider fallaba continuamente. La solución inmediata (`DOCKER_API_VERSION=1.44` en env vars) no funciona porque el Go client de Traefik hace su propia negociación y no respeta esa variable.

### Causa 2 — Dependencia de Docker provider para middleware de auth
El middleware `hg-forwardauth` estaba definido SOLO mediante labels Docker del container del forwardauth proxy. Al remover el Docker provider, la definición desapareció. No existía copia en file provider.

### Causa 3 — Tenants sin bind mount desde el inicio
La función `create-hosting` para sitios estáticos nginx nunca agregaba `-v /opt/clients/{name}:/usr/share/nginx/html:ro`. El contenido se subía via ZIP y se copiaba al container con `docker cp`, quedando en la capa writable del container. Al recrear el container (por cualquier motivo), el contenido se perdía silenciosamente.

### Causa 4 — Router health no verificaba body content
El health check verificaba solo HTTP status code. HTTP 200 + "Welcome to nginx!" = false positive healthy. El sistema reportó 100% healthy mientras un sitio servía contenido por defecto.

### Causa 5 — `/opt/traefik-dynamic/` no escribible desde app/scheduler
El directorio estaba montado `:rw` pero el host lo tenía con permisos 0755 (root). Los containers (non-root) no podían escribir, causando que la generación automática de YAML fallara silenciosamente.

---

## Diagnósticos equivocados

### ❌ "Es un problema de DNS"
**Por qué parece posible:** Las URLs no responden.  
**Por qué es incorrecto:** `dig` y `nslookup` resuelven correctamente. El problema está en Traefik, no en DNS.  
**Señal discriminante:** DNS resuelve → el problema está en la capa de routing (Traefik).

### ❌ "Traefik restart va a solucionar"
**Por qué parece posible:** El restart limpia estado en memoria.  
**Por qué es incorrecto:** El Docker provider sigue fallando después del restart porque el problema es la versión de API, no estado corrupto.  
**Señal discriminante:** El error persiste exactamente igual después del restart.

### ❌ "DOCKER_API_VERSION=1.44 es la solución"
**Por qué parece posible:** Es una env var documentada.  
**Por qué es incorrecto:** El cliente Go de Traefik hace su propia negociación y no respeta esa variable de entorno.  
**Señal discriminante:** El error persiste después de agregar la variable.

### ❌ "mi-academia está ok — HTTP 200"
**Por qué parece posible:** El status code es 200.  
**Por qué es incorrecto:** El body contiene "Welcome to nginx!" — página por defecto sin contenido real.  
**Señal discriminante:** Verificar body, no solo status.

---

## Solución aplicada

```bash
# 1. Remover Docker provider de Traefik (en /opt/deploy/docker-compose.yml)
# Eliminar líneas: --providers.docker=true, --providers.docker.network=..., --providers.docker.exposedbydefault=false

# 2. Recrear Traefik
docker compose up -d traefik

# 3. Crear definición de middleware via file provider
cat > /opt/traefik-dynamic/tenant-forwardauth-middleware.yml << 'EOF'
http:
  middlewares:
    hg-forwardauth:
      forwardAuth:
        address: "http://hg-forwardauth:4181"
        authResponseHeaders:
          - "X-Forwarded-User"
          - "X-Forwarded-Email"
EOF

# 4. Migrar todos los YAMLs de @docker a @file
for f in /opt/traefik-dynamic/tenants-active.yml; do
  sed -i 's/@docker/@file/g' "$f"
done

# 5. Eliminar ruta de smoke test sin auth
rm /opt/traefik-dynamic/tenant-smoke-mi-test.yml

# 6. Fix permisos del directorio
chmod 777 /opt/traefik-dynamic

# 7. Recrear container con mount
docker stop user_1_mi_academia
docker rm user_1_mi_academia
docker run -d \
  --name user_1_mi_academia \
  --network deploy_hosting_network \
  --restart unless-stopped \
  -v /opt/clients/user_1_mi_academia:/usr/share/nginx/html:ro \
  nginx:alpine
```

---

## Fix permanente

### 1. `create-hosting` siempre crea bind mount
```python
# app/api/routes/hosting.py — create-hosting endpoint
host_site_dir = f"/opt/clients/{container_name}"
os.makedirs(host_site_dir, exist_ok=True)
# docker run ... -v /opt/clients/{container_name}:/usr/share/nginx/html:ro ...
```

### 2. Router health verifica body content
```python
# app/services/router_health_guard.py
# _http_check() retorna body bytes
# _is_nginx_default_page() detecta "Welcome to nginx!"
# → genera incidente misconfigured_site_content
```

### 3. check_static_container_mounts() job diario
Detecta containers nginx activos sin bind mount → genera incidente `invalid_container_mount`.

### 4. `tenant-forwardauth-middleware.yml` como archivo protegido
Incluido en `_PLATFORM_FILES` y `_PLATFORM_PROTECTED_FILES`. El job verifica su existencia y contenido.

### 5. `ensure_static_container_mount()` endpoint de reparación
`POST /admin/router-health/tenants/{id}/static-repair` — dry_run + live repair con precondiciones.

### 6. Upload writability check antes de aceptar ZIP
```python
if not os.access(site_dir, os.W_OK):
    raise HTTPException(503, {"code": "import_dir_not_writable"})
```

---

## Qué debería haber hecho la IA

Con el runbook TRAEFIK_CLIENT_VERSION_TOO_OLD disponible:

1. Al ver `client version 1.24 is too old` → match inmediato → runbook TRAEFIK_CLIENT_VERSION_TOO_OLD
2. Runbook dice: "DOCKER_API_VERSION env var no funciona en Traefik Go client — no intentarlo"
3. Runbook dice: acción segura = `remove_docker_provider_from_traefik_config`
4. Runbook dice: acción prohibida = `auto_restart_traefik_without_config_backup`
5. Al ver "Welcome to nginx!" → match inmediato → WELCOME_TO_NGINX_EMPTY_SITE
6. Runbook dice: verificar Mounts=[] y /opt/clients/{name}/index.html antes de reparar
7. Runbook dice: acción segura = `recreate_static_nginx_container_with_mount`
8. Diagnóstico total: < 5 minutos vs 4 horas

---

## Runbooks nacidos de este incidente

| Runbook ID | Lección aprendida |
|---|---|
| TRAEFIK_CLIENT_VERSION_TOO_OLD | API version mismatch en Go client |
| TRAEFIK_DOCKER_PROVIDER_UNHEALTHY | Docker provider es un single point of failure |
| FORWARDAUTH_MIDDLEWARE_DOCKER_MISSING | Middleware @docker desaparece sin Docker provider |
| FILE_PROVIDER_FORWARDAUTH_MIGRATION | Migración @docker → @file debe ser atómica |
| WELCOME_TO_NGINX_EMPTY_SITE | HTTP 200 no implica contenido correcto |
| CONTAINER_WITH_EMPTY_MOUNTS | Mounts=[] = contenido efímero |
| TRAEFIK_DYNAMIC_DIR_RW_DENIED | Permisos de host vs container user |
| DASHBOARD_FALSE_100_HEALTH | Status code no es suficiente health check |
| ROUTER_HEALTH_INCIDENTS_DELETED_BY_SYNC | source_type como firewall para sync handlers |

---

## Chaos tests derivados

```bash
scripts/chaos/002_break_docker_provider.sh     # → debe detectar TRAEFIK_DOCKER_PROVIDER_UNHEALTHY
scripts/chaos/003_missing_forwardauth_middleware.sh  # → debe detectar FORWARDAUTH_MIDDLEWARE_DOCKER_MISSING
scripts/chaos/004_tenant_public_404.sh          # → debe detectar TENANT_PUBLIC_404_ROUTER_MISSING
scripts/chaos/005_welcome_to_nginx.sh           # → debe detectar WELCOME_TO_NGINX_EMPTY_SITE
scripts/chaos/006_empty_mounts_static_container.sh  # → debe detectar CONTAINER_WITH_EMPTY_MOUNTS
```

---

## Lecciones aprendidas

1. **Diagnóstico desde cero cuesta horas.** Con runbooks, este incidente dura < 30 min.
2. **HTTP 200 no es health.** Body check es obligatorio para sitios estáticos.
3. **Un solo provider para routing es más simple que dos.** Docker provider + file provider = doble superficie de fallo.
4. **Middleware de auth debe existir en file provider, no solo en Docker labels.**
5. **`create-hosting` debe ser idempotente respecto al mount.** Si el directorio existe, el bind mount debe existir siempre.
6. **Permisos de host directory importan** aunque el volumen esté montado `:rw`.
7. **El `DOCKER_API_VERSION` env var no funciona para el Go client de Traefik.** Documentado y en runbook.
