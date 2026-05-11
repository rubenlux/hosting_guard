Aquí tienes una explicación completa y detallada del archivo app/api/main.py:

📁 app/api/main.py — Punto de entrada principal de la API
Este archivo es el corazón de la aplicación. Define la instancia de FastAPI, registra todos los middlewares, y declara todos los endpoints del sistema HostingGuard.

1. 📦 Importaciones
Se importan tres grandes grupos de dependencias:

Librerías estándar/externas: fastapi, slowapi (rate limiting), prometheus_client (métricas), bcrypt (hashing de contraseñas), jose (JWT).
Módulos internos del dominio: pipeline de decisiones, motor de ejecución, orquestador de IA, RAG (Retrieval-Augmented Generation), repositorios de auditoría.
Infraestructura: repositorios SQLite, configuración de tenants, métricas de Prometheus.
2. ⏱️ Scheduler de Expiración (expiration_scheduler)
Python

Apply
async def expiration_scheduler():
Es una tarea asíncrona en background que se ejecuta cada 12 horas.
Llama a check_and_expire_free_hostings() para deshabilitar hostings gratuitos caducados.
Si falla, registra el error en logs pero no detiene la app.
3. 🚀 Ciclo de vida de la app (lifespan)
Python

Apply
@asynccontextmanager
async def lifespan(app):
    asyncio.create_task(expiration_scheduler())
    yield
Al iniciar la app, lanza el scheduler en segundo plano.
Usa el patrón moderno de FastAPI para gestionar el ciclo de vida (reemplaza on_startup).
4. 🏗️ Instancia de FastAPI
Python

Apply
app = FastAPI(title="Hosting Guard API", version="1.16.0", ...)
Crea la aplicación con título, descripción y versión.
Registra el lifespan definido arriba.
5. 🔐 Autenticación y Usuarios
POST /register
Recibe email y contraseña.
Aplica doble hashing: primero SHA-256, luego bcrypt.
Guarda el usuario en la base de datos a través de UserRepository.
POST /login
Verifica credenciales con el mismo doble hashing.
Si son válidas, devuelve un access token (JWT de corta duración) y un refresh token.
POST /refresh
Recibe un refresh token, lo decodifica con jose.
Verifica que sea de tipo "refresh" y emite un nuevo access token.
GET /me
Endpoint protegido (Depends(verify_token)).
Devuelve los datos del usuario autenticado: plan, balance, métodos de pago, etc.
Si el token es válido pero el usuario no existe en la DB, devuelve 401 (útil si se limpia la base de datos).
6. ⚙️ Configuración de Usuario
POST /user/config
Permite al usuario actualizar sus preferencias: autoscale_enabled y has_payment_method.
POST /user/topup
Recarga saldo (balance) en la cuenta del usuario.
GET /advisory
Retorna una lista mock de eventos de monitoreo (aumento de CPU, SSL renovado, intrusiones bloqueadas). Sirve para el dashboard.
7. 🛡️ Middlewares (capas de seguridad y control)
Se añaden en este orden:
Middleware	Propósito
SecurityHeadersMiddleware	Añade cabeceras de seguridad HTTP (CSP, HSTS, etc.)
CORSMiddleware	Permite peticiones desde el frontend (hostingguard.lat, localhost:5173)
SlowAPIMiddleware	Habilita el sistema de rate limiting
8. 🧠 Infraestructura de IA y Auditoría
Se instancian los repositorios y motores principales:

AuditRepository: guarda decisiones (append-only).
HumanActionRepository: guarda acciones tomadas por humanos.
ExecutionRepository: audita ejecuciones de acciones técnicas.
TenantConfigRepository: gestiona configuraciones versionadas por tenant.
AIOrchestrator: combina RAG por tenant + LLM dinámico (se elige por variable de entorno).
ExecutionEngine: motor que ejecuta acciones técnicas aprobadas.
9. 🔄 Endpoint Principal: POST /decision
Python

Apply
@app.post("/decision", response_model=DecisionResponse)
@limiter.limit("30/minute")
def make_decision(...)
Este es el endpoint más importante del sistema. Su flujo es:

Ejecuta el pipeline de decisión (run_decision_pipeline) con los síntomas y contexto del hosting.
Genera un advisory base con generate_advisory.
Si el feature flag ENABLE_AI_ADVISORY está activo, enriquece el advisory con IA (ai_orchestrator.enrich).
Registra métricas en Prometheus: total de decisiones, estado, latencia.
Persiste el evento en auditoría (append-only, nunca se borra).
Loguea en formato JSON para auditoría de seguridad por tenant (IP, decision_id, status).
Devuelve la decisión enriquecida con tenant_id y advisory.
10. 🙋 POST /decision/action
Registra una acción tomada por un humano sobre una decisión (aprobar, rechazar, etc.).
Incrementa métricas de interacción humana en Prometheus.
11. ⚡ POST /decision/execute
Ejecuta una acción técnica sobre la infraestructura.
Doble protección:
Feature flag ENABLE_ACTION_EXECUTION (si está desactivado, retorna 403).
La acción debe tener requires_human_approval = true (garantiza que un humano la revisó).
Audita el resultado de la ejecución en ExecutionRepository.
12. 🏢 POST /tenant/config
Endpoint administrativo para crear nuevas versiones de configuración (reglas o prompts) para un tenant específico.
⚠️ El comentario indica que debe protegerse en producción (actualmente no tiene autenticación).
13. 📊 GET /metrics
Expone todas las métricas de Prometheus en formato texto plano.
Consumido por Prometheus/Grafana para monitoreo.
14. ❤️ GET /health
Health check básico que retorna {"status": "ok"}.
Usado por balanceadores de carga y orquestadores como Docker/Kubernetes.
🗺️ Resumen Visual

Apply
main.py
├── Autenticación       → /register, /login, /refresh, /me
├── Usuario             → /user/config, /user/topup, /advisory
├── Decisiones IA       → /decision (pipeline + IA + auditoría + métricas)
├── Acciones Humanas    → /decision/action
├── Ejecución Técnica   → /decision/execute (feature-flagged)
├── Multi-tenancy       → /tenant/config
├── Observabilidad      → /metrics, /health
└── Background Tasks    → expiration_scheduler (cada 12h)


---

## Cambios — 2026-05-07

### Backend: GitHub Deploy extendido (`app/api/routes/hosting.py`)

- **`GitDeployRequest`** ampliado con 9 campos nuevos: `root_directory`, `install_command`, `build_command`, `start_command`, `output_directory`, `port`, `framework`, `dockerfile_path`, `env_vars`
- **3 estrategias de deploy**:
  - A: Dockerfile (`dockerfile_path` o `framework=dockerfile`) → `docker build` + `docker run`
  - B: App server (`start_command`) → imagen base + `sh -c "install && start"`
  - C: Static/Node → detección de `package.json` + `serve`, o nginx puro
- **`git_config` + `webhook_token`** persistidos en DB después del deploy
- **`deploy_log`** con stages por deploy almacenado en `deploy_logs` JSONB
- **Redeploy mejorado** (`POST /hostings/{id}/redeploy`): usa `git_config` almacenado; Dockerfile → rebuild completo; demás → git pull + restart
- **Webhook** (`POST /hostings/{id}/webhook`): validación HMAC SHA-256 contra `webhook_token`, solo dispara en eventos `push`, triggerea redeploy automático
- **Deploy logs** (`GET /hostings/{id}/deploy-logs`): retorna últimos 10 deploys

### Backend: Dominios propios

**`app/infra/migrations.py`**
- Tabla `custom_domains` con columnas: `domain_id`, `user_id`, `hosting_id`, `domain`, `domain_type`, `dns_status`, `ssl_status`, `verified_at`, `last_checked_at`, `error_message`, `verification_token`, `is_primary`
- Columnas `git_config JSONB`, `webhook_token TEXT`, `deploy_logs JSONB` en tabla `hostings`
- Índices en `custom_domains`

**`app/infra/audit/domain_repository.py`** (nuevo)
- `add_domain`, `get_domains`, `get_domain`, `get_by_domain_name`
- `update_status` (keyword-only args para dns_status, ssl_status, error_message, verified)
- `set_primary`, `delete_domain`, `get_pending_domains` (JOIN con hostings, retorna dominios pendientes no chequeados en 5 min)

**`app/infra/audit/hosting_repository.py`**
- `set_git_config(hosting_id, git_config, webhook_token)` 
- `get_git_config(hosting_id, user_id)` → devuelve git_config + webhook_token
- `get_by_webhook_token(token)` → lookup interno para webhook
- `get_for_webhook(hosting_id)` → lookup sin filtro user_id para validación HMAC
- `append_deploy_log(hosting_id, entry)` → append a JSONB array
- `get_deploy_logs(hosting_id, user_id)` → últimos 10

**`app/services/domain_checker.py`** (nuevo)
- `verify_dns(domain, subdomain)` → compara IP via `socket.gethostbyname()` contra `SERVER_IP` (A record) o IP del subdominio (CNAME chain)
- `dns_instructions(domain, subdomain)` → instrucciones CNAME o A según tipo de dominio (apex vs subdominio)
- `write_traefik_config(domain_id, domain, container_name, port, redirect_www)` → escribe YAML en `TRAEFIK_DYNAMIC_DIR`; incluye router HTTP→HTTPS y router HTTPS con Let's Encrypt
- `remove_traefik_config(domain_id)` → elimina YAML
- `check_pending_domains()` → job para scheduler, verifica todos los dominios pending/failed

**`app/api/routes/custom_domains.py`** (nuevo)
- `GET /hostings/{id}/domains` → lista dominios del hosting
- `POST /hostings/{id}/domains` → agrega dominio (valida no sea subdominio nuestro, no esté duplicado), devuelve instrucciones DNS
- `DELETE /hostings/{id}/domains/{domain_id}` → elimina dominio + config Traefik
- `POST /hostings/{id}/domains/{domain_id}/verify` → verifica DNS manualmente; si OK escribe Traefik config + SSL
- `POST /hostings/{id}/domains/{domain_id}/set-primary` → marca como primario (solo dominios activos)
- Usa `log_event` de `app.services.activity_service` (no ActivityRepository que no existe)

**`app/api/config.py`**
- `SERVER_IP = os.getenv("SERVER_IP", "")` → IP pública del servidor para verificación A record apex

**`app/api/main.py`**
- Registrado `custom_domains_router`

**`app/services/scheduler_runner.py`**
- Job `check_pending_domains` cada 300s (5 min)
- Job count actualizado a 15

### Bug crítico corregido
- `custom_domains.py` y `domain_checker.py` importaban `ActivityRepository` de un módulo inexistente (`app.infra.audit.activity_repository`) → server crash al iniciar. Corregido a `log_event` de `app.services.activity_service`.

### Frontend: Dominios propios

**`frontend/src/components/dashboard/sections/DomainsSection.jsx`** (reescrito)
- Componente `DomainManager` por hosting: add/delete/verify/set-primary via API real
- Panel de instrucciones DNS dinámico (se muestra al agregar o si verificación falla)
- Badges de estado: `dns_status` (pending/active/failed) + `ssl_status`
- Botón "Verificar" manual, botón "Primario" para dominios activos
- Input con validación, mensajes de error inline

**`frontend/src/services/api.js`**
- `redeployHosting(id)`, `getDeployLogs(id)`
- `getDomains(hostingId)`, `addDomain(hostingId, domain)`
- `deleteDomain(hostingId, domainId)`, `verifyDomain(hostingId, domainId)`
- `setPrimaryDomain(hostingId, domainId)`
- `deployFromGithub` actualizado para aceptar `extra` config (todos los campos avanzados)

### Frontend: GitHub Deploy — configuración avanzada

**`frontend/src/components/HostingCreationForm.jsx`**
- Sección "Configuración avanzada" colapsable en el formulario GitHub
- Campos: `root_directory`, `install_command`, `build_command`, `start_command`, `output_directory`, `port`, `dockerfile_path`
- Editor de variables de entorno: pares key/value dinámicos (agregar/eliminar filas)
- Todos los campos son opcionales; se pasan al backend solo si tienen valor

### Frontend: Facturación — nuevos planes

**`frontend/src/components/dashboard/sections/BillingSection.jsx`**
- Agregado plan **Agencia Pro** ($59/mes, $708/año) con color naranja (#f97316)
- Features actualizadas para todos los planes (copiadas de `Pricing.jsx`)
- Grilla de upgrade: ahora muestra 4 columnas (Personal / Negocio / Agencia / Agencia Pro)
- Bloque **Enterprise** ($99/mes anual, $129 mensual) con toggle Anual/Mensual, features en 2 columnas, botón de checkout
- `PLAN_ORDER` extendido: `['free', 'personal', 'negocio', 'agencia', 'agencia_pro', 'enterprise']`

---

## Cambios — 2026-05-07 (continuación)

### Frontend: DomainsSection — mini guía para usuarios no técnicos

**`frontend/src/components/dashboard/sections/DomainsSection.jsx`**
- Pill superior con dominio temporal (`Tu dominio temporal: X.hostingguard.lat`) en verde
- Mini guía **"Conectar tu dominio en 3 pasos"** visible siempre antes del input:
  - Paso 1 (azul): Agregá tu dominio
  - Paso 2 (violeta): Copiá el registro DNS
  - Paso 3 (verde): Verificá y activá SSL
- Nota destacada: "No necesitás transferir tu dominio ni cambiar de proveedor"
- Sección **"¿Dónde configuro esto?"** con lista de proveedores: Cloudflare, GoDaddy, Namecheap, DonWeb, Nic Argentina, Hostinger
- Chips clickeables con ejemplos válidos (`ejemplo.com`, `www.ejemplo.com`, `app.ejemplo.com`) — se ocultan cuando el usuario empieza a escribir
- Hint de tipo en tiempo real (`→ Dominio raíz` / `→ Subdominio`) al tipear
- Instrucciones post-agregar etiquetadas como **"Paso 2"** con nota de propagación DNS

### Frontend + Backend: Detección apex/subdominio con TLDs compuestos

**Problema:** `canela-app.com.ar` se detectaba como subdominio (lógica naive `split('.').length === 2`).

**`frontend/src/components/dashboard/sections/DomainsSection.jsx`**
- Eliminadas `isApex` y `subLabel` naive
- Añadido `COMPOUND_TLDS` (Set JS) con 40+ entradas: `.com.ar`, `.net.ar`, `.co.uk`, `.com.au`, `.com.br`, `.com.mx`, `.co.nz`, `.co.za`, `.co.jp`, `.com.cn`, `.com.hk`, `.com.sg`, etc.
- `getRegistrableDomain(domain)`: si los últimos 2 labels están en `COMPOUND_TLDS` y hay al menos 3 labels → toma 3 labels como dominio registrable; si no, toma 2
- `isApex(domain)`: `d === getRegistrableDomain(d)`
- `subLabel(domain)`: `d.slice(0, d.length - registrable.length - 1)` — ahora retorna `www` para `www.canela-app.com.ar` (antes retornaba `www.canela-app`)

**`app/services/domain_checker.py`**
- Añadido `_COMPOUND_TLDS` (frozenset Python) con las mismas entradas
- `_registrable_domain(domain)`: misma lógica que el frontend
- `_is_apex(domain)`: `d == _registrable_domain(d)`
- `dns_instructions()`: reemplazado `domain.count(".") == 1` por `_is_apex(domain)`

**Acceptance confirmado:**
| Dominio | Resultado |
|---|---|
| `canela-app.com.ar` | apex → A record |
| `www.canela-app.com.ar` | subdominio → CNAME |
| `app.canela-app.com.ar` | subdominio → CNAME |
| `ejemplo.com` | apex → A record |
| `www.ejemplo.com` | subdominio → CNAME |

### Backend: Validación completa GitHub Deploy avanzado

**Resultados por caso:**

| Caso | Estrategia | Veredicto |
|---|---|---|
| Static root `.` | C (node build) | PASS |
| Frontend `/frontend` | C (node build) | PASS |
| Monorepo `/apps/web` | C (node build) | PASS |
| FastAPI `/backend` | B (app server) | PASS |
| Dockerfile `/backend/Dockerfile` | A (Dockerfile) | PASS |

**Webhook:**
- Sin firma → 401
- Firma inválida → 401
- Firma válida + evento no-push → 200 ignored
- Firma válida + push → redeploy ejecutado, `triggered_by: "webhook"` en deploy_log

### Bug crítico corregido — Path traversal en GitHub Deploy

**`app/api/routes/hosting.py`** — 3 vulnerabilidades encontradas y corregidas:

**BUG 1 — `root_directory` path traversal (CRÍTICO)**
- Causa: `os.path.join(site_dir, "../../etc")` escapaba el repo clonado y se montaba como volumen Docker en el contenedor del usuario
- Fix: `os.path.realpath()` + check `startswith(real_site + os.sep)` post-clone; si falla, limpia `site_dir` y devuelve 400

**BUG 2 — `dockerfile_path` path traversal (CRÍTICO)**
- Causa: `docker build -f {work_dir}/../../etc/hosts` podía leer archivos fuera del repositorio
- Fix: mismo patrón `realpath` contra `_real_work` antes de invocar `docker build`

**BUG 3 — `output_directory` path traversal en nginx (MODERADO)**
- Causa: `os.path.join(work_dir, "../../etc")` se usaba como fuente del volumen `-v path:/usr/share/nginx/html:ro` montando un path arbitrario del host
- Fix: mismo patrón `realpath` antes de construir el comando Docker

Todos los checks limpian el `site_dir` clonado antes de devolver el error 400 para evitar residuos en disco.

---

## Cambios — 2026-05-08

### Backend: GitHub Deploy — fix Create React App / TLDs compuestos en subdirectorios

**Caso real detectado:** repo `PI-countries` con `client/public/index.html` (plantilla CRA) era tomado como output publicable. El sitio real está en `client/build/index.html` luego del build.

**`app/api/routes/hosting.py`** — 5 cambios:

**1. `_find_serve_dir` — eliminar `public` de candidatos**
- `public` fue removido de la lista de directorios buscados. Era la primera opción y coincidía con la plantilla de Create React App, causando que se sirviera la plantilla de desarrollo en lugar del build.
- Lista actualizada: `["dist", "build", "www", "_site", "frontend/dist", "out"]`

**2. Strategy C (node build) — arquitectura dos fases**
- Antes: un solo `docker run -d sh -c "npm install && npm run build && npx serve dist"` — si el build fallaba, el deploy retornaba OK igual porque el contenedor arrancaba en background.
- Ahora:
  - **Fase 1**: `docker run --rm` sincrónico para install + build. Si falla, limpia `site_dir` y devuelve 500 con error de build.
  - **Fase 2**: Verifica que `{output_directory}/index.html` exista en el host. Si no existe, falla con mensaje claro: `"No encontramos index.html en el output configurado ({dir}). En Create React App normalmente es build; en Vite normalmente es dist."`
  - **Fase 3**: Lanza `nginx:alpine` con `-v {serve_root}:/usr/share/nginx/html:ro` — más eficiente que `npx serve`, nunca sirve la plantilla.

**3. Auto-detección de `output_directory`**
- Si `data.output_directory` no está especificado, se detecta automáticamente desde `package.json`:
  - `react-scripts` en deps o en build script → `build/`
  - `vite` en deps o en build script → `dist/`
  - Otros → auto-detect post-build buscando `build`, `dist`, `out`, `_site`

**4. Deploy log detallado**
- `build_info`: `root_directory`, `package_json` (bool), `install_command`, `build_command`, `output_directory`
- `build`: stdout/stderr del build (3000 chars)
- `output_check`: `output_directory` resuelto + `index_html_found` (bool)
- `container`: resultado del `docker run nginx`

**5. `strategy` en `git_config` + redeploy correcto**
- Se persiste `strategy: "dockerfile" | "server" | "static_built" | "static_pure"` en `git_config` al hacer el deploy inicial.
- Redeploy y webhook ahora usan `strategy`:
  - `dockerfile` → rebuild completo Docker
  - `static_built` → re-ejecuta `docker run --rm npm install && build`, luego `docker restart nginx`
  - `server` / `static_pure` → `docker restart` (archivos ya actualizados por git pull)
- Antes del fix, un redeploy de una app React no re-buildea: hacía `docker restart` del contenedor `npx serve` (que servía el build anterior).

**Acceptance case resuelto:**
- `Root Directory: client`, `Install Command: npm install --legacy-peer-deps`, `Build Command: CI=false NODE_OPTIONS=--openssl-legacy-provider npm run build`, `Output Directory: build`
- Deploy: fase 1 build → fase 2 encuentra `client/build/index.html` → fase 3 nginx sirve `client/build/` → PASS
- Si falta `client/build/index.html`: falla antes de lanzar nginx, nunca queda en 403.

---

## 2026-05-08 — CORS real, /admin/staff 500, terminate hosting, zona peligrosa usuario, path traversal

### BLOQUE 1 — /admin/staff corregido (staff_repository.py)

**Problema:** `GET /admin/staff` devolvía 500 con traceback:
```
psycopg2.errors.UndefinedColumn: column "created_at_ts" does not exist
HINT: Perhaps you meant to reference the column "staff_accounts.created_at".
```
El navegador mostraba esto como "CORS error" porque la respuesta 500 no tenía headers CORS (antes del fix de orden de middlewares).

**Root cause:** La migración define `created_at TEXT NOT NULL` tanto en `staff_accounts` como en `staff_activity_log`, pero `staff_repository.py` referenciaba `created_at_ts` en todas sus queries (INSERT, SELECT, ORDER BY, WHERE, EXTRACT).

**Fix:** Reemplazados todos los usos de `created_at_ts` por `created_at` en `app/infra/audit/staff_repository.py` (9 locations). Eliminados alias redundantes `l.created_at AS created_at` en queries con `l.*`.

### BLOQUE 2 — CORS en respuestas de error

**Estado:** Ya en producción desde sesión anterior.
- `SlowAPIMiddleware` se registra antes que `CORSMiddleware` → CORS envuelve rate-limiting → 429s tienen CORS headers.
- `@app.exception_handler(Exception)` (global_exception_handler, `app/api/main.py` línea 1125) captura excepciones dentro de `ExceptionMiddleware`, que está dentro de `CORSMiddleware` → 500s tienen CORS headers.
- Con el fix del BLOQUE 1, el 500 de `/admin/staff` ya no ocurre.

### BLOQUE 3 — Admin terminate limpia custom_domains

**Problema:** `DELETE /admin/hostings/{id}/terminate` no limpiaba:
1. Archivos de configuración de Traefik para dominios propios
2. Registros en tabla `custom_domains`
3. Activity event en `activity_events`

**Fix en `app/api/routes/admin.py`:**
- Paso 2 nuevo: obtiene todos los dominios del hosting via `DomainRepository.get_domains()`, llama `remove_traefik_config()` por cada uno y `delete_domain()`.
- Paso 4 nuevo: llama `log_event()` con `event_type="hosting_terminated_by_admin"`, severity="critical".
- Añadido `import logging` + `logger = logging.getLogger(__name__)` al archivo.

### BLOQUE 4 — Usuario final puede eliminar su hosting

**Implementado en sesión anterior (completado hoy):**

Backend `app/api/routes/hosting.py`:
- `POST /hostings/{hosting_id}/terminate` con `verify_token`, ownership check, rate-limit 3/hour.
- Limpia custom_domains (Traefik + DB) antes de eliminar hosting.
- Registra `hosting_termination_requested` en activity log.
- Llama `_do_delete_hosting()` para teardown completo.

API service `frontend/src/services/api.js`:
- `terminateHosting(hostingId, reason, description)` → `POST /hostings/{id}/terminate`.

Frontend `frontend/src/components/dashboard/sections/ConfigSection.jsx`:
- Nueva sección "Zona peligrosa" con selector de hosting, razón (4 opciones), descripción opcional, confirmación por nombre de proyecto.
- Acepta prop `onHostingDeleted()` — al terminar, espera 1.8s y llama callback.
- 401 detectado → mensaje "Sesión expirada".

`frontend/src/pages/Dashboard.jsx`:
- Pasa `onHostingDeleted={() => { refresh(); setSidebarSection(null); navigate('/sites'); }}` a ConfigSection.
- Al eliminar: actualiza lista de hostings + navega a Mis Sitios.

`frontend/src/pages/AdminDashboard.jsx` (TerminateModal):
- 401 detectado → muestra "Sesión expirada. Volvé a iniciar sesión e intentá de nuevo."

### BLOQUE 5 — GitHub Deploy estático (PI-countries)

**Estado:** Ya implementado en sesión anterior (validado hoy).
- Dos fases: build → validación de `index.html` → nginx.
- `public/` excluido de `_find_serve_dir`.
- Auto-detección: `react-scripts` → `build`, `vite` → `dist`.
- Path traversal: `root_directory`, `dockerfile_path`, `output_directory` protegidos con `os.path.realpath()` + `startswith(real_base + os.sep)`.
- Caso PI-countries: `root_directory=client`, `output_directory=build` → sirve `client/build/` vía nginx sin 403.

### Archivos modificados
- `app/infra/audit/staff_repository.py`
- `app/api/routes/admin.py`
- `app/api/routes/hosting.py` (ya modificado sesión anterior, verificado)
- `app/api/main.py` (ya modificado sesión anterior, verificado)
- `frontend/src/pages/AdminDashboard.jsx`
- `frontend/src/pages/Dashboard.jsx`
- `frontend/src/components/dashboard/sections/ConfigSection.jsx`
- `frontend/src/services/api.js`

---

## 2026-05-08 — WP Security Pipeline, Activity Timeline fix, path traversal en terminate

### BLOQUE 6 — WordPress Security aggregation pipeline

**Nuevos archivos:**
- `app/services/aggregate_wp_attacks.py` — convierte `activity_events` en `security_events`
  - `_WP_LOGIN_THRESHOLD = 5`, `_XMLRPC_THRESHOLD = 3`, `_WINDOW_MINUTES = 10`
  - ON CONFLICT upsert sobre índice parcial único `uq_open_wp_security_event`
  - Detección created vs updated via `(xmax::bigint = 0) AS is_new`
  - Aislamiento por regla: fallo en xmlrpc no detiene wp_login
  - Returns `(created, updated, skipped)` 3-tuple por regla
- `tests/test_aggregate_wp_attacks.py` — 20 tests (SQL param balance, rule isolation, thresholds, ON CONFLICT, actor_type, metadata)
- `tests/test_activity_service.py` — 9 tests (actor_email isolation, owner_email present, SQL shape)

**Bug crítico corregido — psycopg2 IndexError en xmlrpc:**
- Causa: `WHERE ae.event_type ILIKE '%xmlrpc%'` como literal SQL mezclado con `%s`. psycopg2 interpreta `%x` como especificadores de formato.
- Fix: `WHERE ae.event_type ILIKE %s` con `("%xmlrpc%",)` en params.

**Bug corregido — COALESCE leaking owner email (`activity_service.py`):**
- `COALESCE(ae.actor_email, u.email)` devolvía el email del owner como `actor_email` para eventos externos con `actor_email=NULL`.
- Fix: `CASE WHEN ae.actor_type = 'external' THEN NULL ELSE COALESCE(...) END AS actor_email`
- Agregado `u.email AS owner_email` como campo separado.

**`app/services/collect_wp_log_attacks.py` — enriquecimiento:**
- INSERT hardcodea `actor_type='external'` (antes usaba default `'user'`)
- Metadata enriquecida: `container_name`, `hosting_id`, `source`, `detected_by`, `path`, `method`, `attack_count`, `observed_at`, `source_ip`, `user_agent`
- Fallback `docker logs --since=90s` para contenedores Apache (stdout logging)
- `_LOG_COMBINED_RE` + `_parse_log_line()` para parsear combined log format

**`app/infra/migrations.py`:**
- DELETE deduplicación de `security_events` abiertos
- `CREATE UNIQUE INDEX uq_open_wp_security_event ON security_events (event_type, hosting_id) WHERE status = 'open'`

**`app/services/scheduler_runner.py`:**
- `schedule_job(aggregate_wp_attacks, interval=65, initial_delay=25)` — espera 25s tras arranque para que `collect_wp_log_attacks` complete su primer ciclo

**`app/services/scheduler.py`:**
- `schedule_job()` acepta `initial_delay: int = 0` (asyncio.sleep antes del primer run)

**`app/services/detect_security_anomalies.py`:**
- Removidos `_rule_wp_login_brute_force()` y `_rule_wp_xmlrpc_attack()` (movidos a `aggregate_wp_attacks.py`)

### BLOQUE 7 — Activity Timeline — external events UI fix

**`frontend/src/components/admin/ActivityTimeline.jsx`:**
- Añadida función `actorLabel(e)`: external → `IP: {ip}` o `IP: {metadata.source_ip}` o `'Visitante externo'`; system → `'Sistema'`; demás → `actor_email`
- Badge naranja `externo` para eventos con `actor_type='external'`
- Sección expandida diferenciada: external muestra IP origen, Cliente (`owner_email`), User-Agent; internal muestra Actor, IP
- "Cliente" usa `owner_email` (no `actor_email`) para mostrar el dueño del hosting afectado

### BLOQUE 8 — Path traversal en terminate hosting

**`app/api/routes/admin.py`** y **`app/api/routes/hosting.py`:**
- Validación `os.path.realpath()` + `startswith(safe_base + os.sep)` antes de `shutil.rmtree`
- Si `realpath` escapa `/opt/clients/`, se omite la limpieza del directorio y se registra warning

### Estado de tests al cierre
- **258 passed, 1 skipped**
- Pendiente producción: rebuild del container scheduler para desplegar `collect_wp_log_attacks.py` con `actor_type='external'` y metadata enriquecida. Eventos previos en DB quedan con `actor_type=user` y `metadata={}` (no se modifican retroactivamente).

-----------

40/40. All green.

Here's a summary of the three fixes:

Bug 1 — deleted hosting false positives (_sync_site_alerts)

Changed LEFT JOIN → INNER JOIN hostings + WHERE h.status IN ('active', 'starting', 'stopped', 'error') — deleted hostings are filtered in SQL, never reach the upsert loop
Added a cleanup query that finds open system_incidents for deleted hostings and resolves them with {"resolved_reason": "hosting_deleted", "resolved_by": "sync_incidents_feed"}
Bug 2 — resolved sync not closing incidents (_sync_security_events)

Added LEFT JOIN hostings to the open events query to exclude events for deleted hostings at source
Added the same deleted-hosting cleanup query as site_alerts
By-absence resolution now passes {"resolved_by": "sync_incidents_feed", "source_status": "not_in_open_set"} so you can see in evidence why it was resolved
_resolve_incident extended with optional extra_evidence that does evidence || extra::jsonb
Bug 3 — decision_events schema mismatch

Added 8 ALTER TABLE decision_events ADD COLUMN IF NOT EXISTS statements: user_id, actor_type, action_type, target_type, target_id, decision, reason, metadata. All nullable/defaulted — existing pipeline rows unaffected.
Deploy: sudo git pull origin main && sudo docker compose build scheduler && sudo docker compose up -d scheduler. The init_db() call at scheduler startup will run the ALTER TABLEs idempotently.

--------------------------------

Resumen de cambios:

Bug raíz (hosting.py:1197) — elif not data.root_directory: cambió a if not has_package_json and not data.root_directory:. El elif saltaba la autodetección cuando había un package.json no-web en la raíz (como el backend de PI-countries). Ahora la autodetección corre siempre que el root no sea web-buildable.

Seguridad — Antes de montar cualquier directorio en nginx, se verifica que no contenga .git. Si lo contiene: DeployError(UNSAFE_PUBLISH_ROOT). Para el path estático puro, también se verifica que exista index.html.

_found_dirs — Removido "public" de la lista de directorios candidatos (era el template fuente de CRA, no el build output).

Health check — Después de iniciar el contenedor, espera 2 segundos y hace GET https://{subdomain} con httpx. Si responde 403/404/502/503 → DeployError con diagnóstico específico. Errores TLS/conexión (cert no provisionado aún) se ignoran silenciosamente.

Dashboard refresh (HostingCreationForm.jsx) — onSuccess() ahora se llama inmediatamente en lugar de con setTimeout(..., 2000). El timeout se cancelaba cuando el usuario cerraba el modal antes de los 2 segundos, impidiendo el refresh.

-----------------------------

424 passed, 1 skipped, zero failures. Here's a summary of everything that was done:

app/services/deploy_diagnostics.py — added 5 new error codes (NATIVE_DEPENDENCY_BUILD_FAILED, NODE_SASS_INCOMPATIBLE, NATIVE_BUILD_TOOL_MISSING, NODE_VERSION_MISMATCH, MODULE_NOT_FOUND_BUILD) with severity entries (native_build_tool_missing → "high", rest → "warning").

Dockerfile — added python3 make g++ to the app container's apt-get install.

app/api/routes/hosting.py:

Imports: added the 5 new codes + all 4 functions from build_diagnostics
New helpers: _parse_versions (extracts node/npm version strings from node --version && npm --version output) and _read_version_file (reads .nvmrc or engines.node from package.json)
Phase 1 rewrite: split into two separate docker runs (install, then build), each prefixed with apk add python3 make g++ + version capture; npm logs mounted via -v {tmp_dir}:/root/.npm/_logs; ERESOLVE retry now applies only to the install step; ERR_OSSL retry to the build step; every failure path calls classify_npm_failure, extract_suspected_package, extract_npm_log_path, and read_npm_log to produce rich evidence with node_version, npm_version, suspected_package, stdout_tail, stderr_tail, and the npm debug log tail
tests/test_github_deploy.py — 14 new tests covering all 6 classify_npm_failure rules, both unknown-stage fallbacks, extract_npm_log_path (found and missing), extract_suspected_package, read_npm_log (reads tail, handles not-found), and presence of all 5 new constants.

---

## 2026-05-10 — Refactor deploy service, incidents package, supersede UI, bug idempotencia crítico

### BLOQUE 1 — Refactor app/services/deploy/ (hosting.py 2334 → 1592 líneas)

`app/api/routes/hosting.py` fue partido en módulos de servicio bajo `app/services/deploy/`:

**`app/services/deploy/project_detector.py`** (nuevo, 91 líneas)
- `_find_buildable_roots`, `_detect_out_dir`, `_is_web_buildable`, `_read_pkg`, `_detect_framework`, `_find_serve_dir`

**`app/services/deploy/node_version_detector.py`** (nuevo, 21 líneas)
- `_read_version_file`: lee `.nvmrc` o `engines.node` de `package.json`

**`app/services/deploy/build_runner.py`** (nuevo, 72 líneas)
- `_parse_versions`, `_docker_env_flags`, `_detect_image_for_start`, `_default_install`, `_traefik_labels`, `_check_required_tool`

**`app/services/deploy/github_deploy_service.py`** (nuevo, 663 líneas)
- `run_github_deploy(*, data, user_id, ip_address, project_name, subdomain, container_name, plan)` — pipeline completo; en `DeployError` registra evento y re-raise; en excepción inesperada registra y lanza `HTTPException(500)`

**`app/api/routes/hosting.py`** — `deploy_from_github` reducido a ~30 líneas: valida inputs, computa `subdomain`/`container_name`, llama `run_github_deploy()`, convierte `DeployError` → `JSONResponse`. Los helpers de validación (`_validate_*`, `_enforce_*`) y los helpers de redeploy (`_docker_env_flags`, `_traefik_labels`) permanecen en `hosting.py` porque son usados por otras rutas.

Backward-compat: `hosting.py` re-exporta `_find_buildable_roots`, `_detect_out_dir`, `_is_web_buildable`, `_read_pkg`, `_check_required_tool` en su propio namespace para que los tests existentes sigan importando desde `app.api.routes.hosting`.

---

### BLOQUE 2 — Incidents package (app/services/incidents/)

**`app/services/incidents/incident_deduper.py`** (nuevo, 130 líneas)
- `_normalize_severity`, `_sev_rank`, `_query`, `_upsert_incident`, `_resolve_incident`
- `_upsert_incident`: UPDATE open → si no encuentra, INSERT con `ON CONFLICT (correlation_key) WHERE status = 'open' DO NOTHING`. La severidad solo escala, nunca baja.
- `_resolve_incident(conn, key, extra_evidence=None)`: `UPDATE ... SET status='resolved' ... WHERE correlation_key = ? AND status = 'open'`; si `extra_evidence`, hace `evidence || extra::jsonb`

**`app/services/incidents/sync_security_events.py`** (nuevo) — sincroniza `security_events` → `system_incidents` (source_type='security'). Resuelve por ausencia con evidence `{resolved_by, source_status}`. Limpia incidentes de hostings eliminados.

**`app/services/incidents/sync_site_alerts.py`** (nuevo) — sincroniza `site_alerts` → `system_incidents` (source_type='site'). Resuelve por ausencia y por hosting eliminado.

**`app/services/incidents/sync_system_alerts.py`** (nuevo) — sincroniza `system_alert_events` → `system_incidents` (source_type='system').

**`app/services/incidents/sync_deploy_events.py`** (nuevo) — ver BLOQUE 3.

**`app/services/sync_incidents_feed.py`** — reducido a entrypoint delgado (65 líneas). Importa las 4 funciones del paquete incidents/, las llama en secuencia, agrega counts, loguea totales. Mantiene backward-compat aliases (`_sync_security_events`, `_sync_site_alerts`, etc.) y re-exporta `_GENERIC_DEPLOY_CODES`, `_repo_hash` para tests existentes.

**Tests actualizados** — `tests/test_github_deploy.py`: todos los `patch("app.services.sync_incidents_feed._query/upsert/resolve")` reemplazados por `patch("app.services.incidents.sync_deploy_events._query/upsert/resolve")` porque el mock debe apuntar al módulo donde la función está definida, no donde se importa.

---

### BLOQUE 3 — Bug crítico de idempotencia en sync_deploy_events

**Problema en producción:** `system_incidents` acumulaba registros `build_failed resolved` nuevos cada 2 minutos.

**Causa raíz:**
1. El query principal incluye `build_failed` (17:47) porque no hay un `success` posterior (el único success es del 17:21, anterior al fallo).
2. `_upsert_incident` usa índice parcial `WHERE status = 'open'`: un incidente `resolved` no bloquea un nuevo INSERT → crea incidente nuevo.
3. El post-loop supersede lo resuelve inmediatamente (`node_sass_incompatible` es más específico).
4. Próxima corrida: mismo ciclo. Resultado: N incidentes `build_failed resolved` creciendo infinitamente.

**Fix — `app/services/incidents/sync_deploy_events.py`:**

**1. Pre-filter (antes del upsert):** agrupa `open_rows` por target `(user_id, repo_url, branch, project_name)`. Por cada target, calcula el `last_seen` más reciente de cualquier código específico (no genérico). Los eventos genéricos cuyo `last_seen` sea estrictamente anterior a ese máximo se descartan antes del upsert. Genéricos más nuevos que el específico (nuevo intento) pasan igual.

```
Para cada target:
  latest_specific_ts = max(last_seen de códigos no-genéricos)
  Si genérico.last_seen < latest_specific_ts → skip (no upsert)
```

**2. Fix de `_success_targets` SQL:** antes devolvía todos los successes recientes, incluyendo el de las 17:21 (anterior a los fallos). Ahora incluye solo successes que no tengan un fallo más nuevo para el mismo `(user_id, repo_url)`. El `resolved_reason` en el evidence pasa a ser `"deploy_success"` solo cuando el success es genuinamente posterior al fallo.

**5 tests nuevos agregados (`tests/test_github_deploy.py`):**
1. `test_generic_older_than_specific_not_upserted` — timestamps explícitos 17:47 y 20:48; solo `node_sass_incompatible` es upserteado
2. `test_sync_deploy_idempotent_generic_never_upserted_when_superseded` — 3 corridas consecutivas; `build_failed` nunca upserteado
3. `test_generic_only_is_upserted_when_no_specific_exists` — `build_failed` sin código específico contraparte → sí se upsertea normalmente
4. `test_generic_newer_than_specific_is_upserted` — `build_failed` más nuevo que `node_sass` → sí se upsertea (nuevo intento)
5. `test_success_before_failure_resolves_with_no_recent_failure_reason` — `success_targets` vacío → `resolved_reason = "no_recent_failure"`, no `"deploy_success"`

**Resultado:** 77 → 82 tests, todos verdes. En producción: `build_failed resolved` se congela en el valor actual y no sigue aumentando.

---

### BLOQUE 4 — DeployHistorySection: eventos superseded en el frontend

**`frontend/src/components/dashboard/sections/DeployHistorySection.jsx`**

Añadida función `markSuperseded(events)` que corre en el cliente tras el fetch:
- Itera eventos newest-first
- Por cada `repo_url`, acumula los códigos específicos vistos
- Cuando llega un evento con código genérico (`build_failed`, `npm_install_failed`, `unknown_deploy_error`) y ya existe un código específico para el mismo repo → marca `superseded: true`

**Renderizado de filas superseded:**
- Borde punteado (`border-dashed`), `opacity-40`, texto en grises
- Muestra el código original + badge amber `reemplazado`
- No expandible (sin chevron, sin panel de detalles)
- El evento específico activo (`node_sass_incompatible`) se muestra con estilo normal y expandible

El usuario ve claramente cuál es el problema vigente sin confundirse con diagnósticos anteriores ya superados.

---

## 2026-05-10 — SSL pending post-deploy, UX success card, refactor frontend deploy

### BLOQUE 1 — app/services/deploy/site_health.py (nuevo)

Módulo de probing HTTP post-deploy para manejar el período de provisioning de certificados SSL (Traefik + Let's Encrypt tarda 10-60s después de arrancar el contenedor). Cloudflare devuelve HTTP 526 durante ese período — antes se mostraba al usuario como error.

**`check_site_once(subdomain, timeout=8.0) → dict`**
- Único probe HTTP con `httpx.AsyncClient(verify=False)`
- Retorna `{"http_status": int|None, "error_type": None|"tls"|"connection"|"other"}`
- Captura `ConnectError`, `ConnectTimeout`, `ReadTimeout` → `error_type="connection"`

**`wait_for_site_online(subdomain, timeout_seconds=60, interval_seconds=5) → dict`**
- Polling hasta 2xx, error HTTP fatal, o timeout
- Reglas de clasificación:
  - 2xx → `status="online"` (stop)
  - 403/404/502/503 → `status="http_failed"` (stop inmediato)
  - 526/TLS/connection → `status="ssl_pending"` (seguir esperando)
- Retorna `{status, last_http_status, last_error_type, attempts, duration_seconds}`

---

### BLOQUE 2 — app/services/deploy_diagnostics.py

Agregado:
- `SSL_PROVISIONING_TIMEOUT = "ssl_provisioning_timeout"` como constante de error
- Entrada en `_SEVERITY`: `SSL_PROVISIONING_TIMEOUT: "warning"`

---

### BLOQUE 3 — app/services/deploy/github_deploy_service.py

**Health check reemplazado:**
- Antes: un solo `httpx.AsyncClient.get()` inline con `await asyncio.sleep(2)` y catch-all silencioso
- Después: dos fases separadas:
  1. `check_site_once()` antes del persist a DB (detecta errores HTTP fatales inmediatos)
  2. `wait_for_site_online(timeout_seconds=60)` después del persist (espera SSL activo)

**Manejo de `http_failed` post-persist:** limpia el deploy (container + DB row + client_dir) y registra `deploy_event` antes de re-lanzar `DeployError`.

**SSL pending no bloquea éxito:** si `wait_for_site_online` retorna `ssl_pending`, registra un `deploy_event(stage="ssl_check", status="pending", code=SSL_PROVISIONING_TIMEOUT)` informativo pero retorna éxito al cliente.

**Nuevos campos en el response dict:**
```python
{
  "subdomain":  subdomain,
  "ssl_status": "online" | "pending",
  "message":    "Deploy completado exitosamente." | "Sitio publicado. SSL activándose.",
  # anteriores: status, type, hosting_id, url, repo, branch, webhook_url, webhook_token
}
```

**Imports agregados:** `SSL_PROVISIONING_TIMEOUT`, `check_site_once`, `wait_for_site_online`. Eliminado el bloque `import httpx as _httpx` inline.

---

### BLOQUE 4 — app/api/routes/health.py

Nuevo endpoint `GET /health/{hosting_id}/ssl` registrado ANTES del catch-all `/{hosting_id}`:
- Auth: `verify_token`
- Llama `check_site_once(subdomain)` en tiempo real
- Retorna `{"ssl_status": "online"|"pending", "http_status": int|None, "error_type": str|None}`
- Usado por el frontend para polling del estado SSL en `SslPendingCard`

---

### BLOQUE 5 — frontend: refactor deploy en componentes separados

**Problema:** `HostingCreationForm.jsx` concentraba 5 componentes inline, lógica de error normalization, rate limit countdown, SSL polling y ~670 líneas totales.

**Nueva estructura:**

`frontend/src/hooks/useGithubDeploy.js` (84 líneas):
- Encapsula `deployFromGithub()` + normalización completa de errores
- Retorna `{ deploy, loading, result, reset }`
- `result` tiene campo `kind`:
  - `"success"` → `{hosting_id, subdomain, url, ssl_status, message}`
  - `"rate_limit"` → `{code, detail, retry_after_seconds}`
  - `"diagnostic"` → `{code, stage, detail, suggested_fix, technical_detail, evidence, request_id}`
  - `"runtime_missing"` → mismos campos que diagnostic
  - `"network_error"` → `{detail}` (sin `err.response`)
  - `"generic_error"` → `{error}` (fallback legible)

`frontend/src/components/deploy/` (6 archivos):
- `DeploySuccessCard.jsx` — URL + "Abrir sitio" + "Ir a Mis sitios" (llama `onClose`)
- `SslPendingCard.jsx` — stepper 6 pasos, polling `getSslStatus` cada 5s; cuando online muestra URL y botones
- `DeployDiagnosticCard.jsx` — "Deploy no completado" + `suggested_fix` + `DeployErrorDetails`
- `DeployErrorDetails.jsx` — bloque colapsable con `code/stage/request_id/technical_detail/evidence` en JSON
- `RuntimeMissingCard.jsx` — "El problema no está en tu repo" + detalles internos
- `RateLimitCard.jsx` — countdown autónomo desde `retry_after_seconds` (sin estado externo)

`frontend/src/components/HostingCreationForm.jsx` (405 líneas, −265 vs. antes):
- Orquestador puro: estado del formulario, `useGithubDeploy()`, despacha `onSuccess(data)` inmediatamente
- No cierra el formulario en deploy success — `onClose` solo se dispara desde los botones "Ir a Mis sitios"
- Non-github flows (static/wordpress) mantienen `simpleResult` local, comportamiento idéntico

**Dashboard.jsx:** desacoplado `onSuccess` de close:
```jsx
<HostingCreationForm
  onSuccess={() => refresh()}      // solo refresca Mis Sitios
  onClose={() => setShowCreate(false)}  // cierra al presionar "Ir a Mis sitios"
/>
```

`frontend/src/services/api.js`: agregado `getSslStatus(hostingId)` → `GET /health/{hostingId}/ssl`.

---

### BLOQUE 6 — tests/test_site_health.py (nuevo, 12 tests)

Tests async para `check_site_once` y `wait_for_site_online`:
- 200 → online, 526 → http_status devuelto, ConnectError → connection error
- 502 → http_failed (stop inmediato, 1 intento)
- 526 → 200 → online tras 2 intentos
- timeout con 526 → ssl_pending
- connection error → 200 → online
- `SSL_PROVISIONING_TIMEOUT` constante y severidad correctas
- result tiene todos los campos esperados

**Total:** 82 → 94 tests, todos verdes.