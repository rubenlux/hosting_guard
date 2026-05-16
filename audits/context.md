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

---

## 2026-05-11 — Protection Mode: ForwardAuth, IP blocklist, backfill de contenedores

### BLOQUE 1 — SecurityPolicyResolver (`app/services/security/security_policy_resolver.py`)

- Lee el campo `protection_mode JSONB` de la tabla `hostings` y lo cachea en Redis por 60s (`hg:policy:{hosting_id}`).
- `_derive_mode(pm)`: `enabled=false` → `"off"`; `enabled=true` + cualquier flag de bloqueo → `"protect"`; `enabled=true` sin flags → `"monitor"`.
- `get_policy(hosting_id, conn=None)` → nunca lanza; en fallo de Redis o DB retorna `{"mode": "off"}`.
- `invalidate_policy(hosting_id)` → evicta la clave de Redis; llamado desde `set_protection_mode` en `admin.py`.

### BLOQUE 2 — IP Blocklist (`app/services/security/ip_blocklist.py`)

Redis-backed blocklist con TTL por regla:
- `block_ip(ip, hosting_id, reason, rule_id, ttl_seconds)` → clave `hg:blocklist:{hosting_id}:{ip}`; JSON con reason/rule_id/blocked_at/ttl.
- `is_blocked(ip, hosting_id)` → retorna el JSON o `None`; `None` si Redis no disponible.
- `clear_ip(ip, hosting_id)` → borra la clave.
- Todas las funciones son non-blocking: retornan `False`/`None` si Redis no disponible — sitios nunca caen por fallo de Redis.

### BLOQUE 3 — ForwardAuth endpoint (`app/api/routes/internal.py`)

Traefik llama `GET /internal/forwardauth` en cada request a subdominios de tenant. 200 = permitir, 403 = bloquear.

Flujo:
- Extrae `X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Uri`.
- Cachea resolución subdominio → hosting_id en Redis por 300s (`hg:subdomain:{subdomain}`).
- `mode=off` → 200.
- `mode=protect`: check blocklist → 403; xmlrpc.php → 403; scanner paths (`.env`, `wp-config.php`, etc.) → 403.
- `mode=monitor`: loguea lo que habría bloqueado → 200.

Registrado en `app/api/main.py` como `internal_router`.

### BLOQUE 4 — aggregate_wp_attacks enforcement (`app/services/aggregate_wp_attacks.py`)

Añadida `_maybe_block(ip, hosting_id, rule_id, rule_flag, ttl)`:
- Llama `get_policy()` y `block_ip()` cuando `mode=protect` y el flag correspondiente está activo.
- Cuando `mode=monitor`: loguea IP/rule sin bloquear.
- Llamada desde 3 reglas: `_rule_wp_login` (ttl=3600), `_rule_xmlrpc` (ttl=14400), `_rule_wp_login_rate_limit` (ttl=1800).

### BLOQUE 5 — Traefik wiring

**`app/services/deploy/build_runner.py`** — `_traefik_labels()` añade:
```
"-l", "traefik.http.routers.{name}.middlewares=hg-forwardauth"
```

**`app/api/routes/hosting.py`** — los dos bloques de labels inline (nginx estático línea ~355, WordPress línea ~787) añaden el mismo label de middleware.

**`app/services/domain_checker.py`** — `write_traefik_config()`: router HTTPS file-provider incluye `"middlewares": ["hg-forwardauth@docker"]` (calificador `@docker` requerido porque el archivo YAML es un provider distinto al Docker provider).

**`docker-compose.yml`**:
- Traefik: `--providers.file.directory=/opt/traefik-dynamic` + `--providers.file.watch=true` + volumen `/opt/traefik-dynamic:/opt/traefik-dynamic:ro`.
- App labels: declaración del middleware ForwardAuth:
  ```
  traefik.http.middlewares.hg-forwardauth.forwardauth.address=http://hosting_guard:8000/internal/forwardauth
  traefik.http.middlewares.hg-forwardauth.forwardauth.trustForwardHeader=true
  ```

**Producción** — el `docker-compose.yml` de `/opt/deploy/` se parchó manualmente con `sudo sed` (indentación de 4→6 espacios corregida tras bug del script de parche Python).

### BLOQUE 6 — Tests protection mode (`tests/test_protection_mode.py`)

25 tests: `TestSecurityPolicyResolver` (7), `TestIpBlocklist` (5), `TestForwardAuth` (8), `TestAggregateProtectionEnforcement` (5). Todos verdes.

**Bug de patching resuelto:** `get_redis` se importa localmente dentro de cada función body, no a nivel de módulo. El patch correcto es `app.infra.redis_client.get_redis`, no `app.services.security.security_policy_resolver.get_redis`.

### BLOQUE 7 — Bug crítico: backfill_forwardauth.py perdía bind mounts

**Problema:** `_relabel_container()` nunca leía `HostConfig.Binds`. Al re-crear contenedores sin `-v` flags, nginx servía su página por defecto en lugar del artifact del usuario. Dos contenedores afectados en producción: `user_1_git_matrix-vite-ok_547dd4` y `user_1_git_mi-test_0d3874`.

**`scripts/backfill_forwardauth.py`** — reescrito completamente:

- `_build_docker_run_cmd()`: lee `hc_cfg.get("Binds")` y emite un `-v` por cada bind mount.
- `_validate_binds(binds)`: si algún bind apunta a un nginx html dir, verifica que `index.html` exista en el host; aborta si no.
- `_backup(container, info)`: escribe el JSON completo de `docker inspect` en `/tmp/container-backups/<name>-<ts>.json` antes de cualquier operación destructiva.
- `_merge_middleware(existing, value)`: añade `hg-forwardauth` sin pisar middlewares existentes ni duplicar.
- `_is_tenant_container(name)`: detecta y salta contenedores de infraestructura (`hosting_guard`, `traefik`, `redis`, prefijos `hg_`, `docker_`, etc.).
- `_is_nginx_default(url)`: post-validación tras recrear — detecta regresión a nginx default page.
- Flag `--force`: re-crea incluso contenedores que ya tienen el label (para recovery de bind mounts perdidos).

**`scripts/recover_nginx_mounts.py`** — script dedicado para los dos contenedores rotos:
- Detecta si la imagen es nginx y si le falta el bind `:/usr/share/nginx/html`.
- Verifica `index.html` en `/opt/clients/<container>/dist/` antes de actuar.
- Mismo patrón: backup → stop → rm → run con bind re-añadido → post-validate.
- `KNOWN_BROKEN` lista hardcodeada con los dos containers afectados; también acepta `--container NAME`.

**`tests/test_backfill_forwardauth.py`** — 35 tests, todos verdes:

| Clase | Tests | Cubre |
|---|---|---|
| `TestMountPreservation` | 2 | binds en cmd, sin binds → sin `-v` |
| `TestAbortOnMissingIndexHtml` | 3 | index faltante, index presente, non-html pass |
| `TestAbortOnMissingHostPath` | 1 | host path inexistente falla |
| `TestMiddlewareMerge` | 4 | append, no-duplicate, empty, múltiples |
| `TestDryRun` | 1 | no llama docker, muestra mounts |
| `TestRecreateCommandHasVolume` | 1 | `-v` en cmd |
| `TestNginxRegressionDetection` | 3 | detecta default, no false positive, network error |
| `TestHostingIdFilter` | 1 | filtra por hosting_id |
| `TestNonTenantSkip` | 13 | 10 infra names, 3 tenant names |
| `TestApiAndFrontendSkip` | 3 | hosting_guard, frontend, hg_ prefix |
| `TestSkipAlreadyLabeled` | 2 | skip sin --force, recreate con --force |
| `TestFullRelabelFlow` | 1 | flujo completo: backup + stop + rm + run con bind y middleware |

**Procedimiento de recovery en producción:**
```bash
# Dentro del app container:
python scripts/recover_nginx_mounts.py --dry-run   # verificar primero
python scripts/recover_nginx_mounts.py             # aplicar
curl -s https://matrix-vite-ok.hostingguard.lat | head -5  # no debe decir "Welcome to nginx"

# Luego backfill al resto:
python scripts/backfill_forwardauth.py --dry-run
python scripts/backfill_forwardauth.py
```

62/62. The IDE diagnostics are all Pylance hints (unused vars in lambdas, unresolved import due to scripts/ not being a standard package) — none cause runtime errors.

Here's what changed in the new design and what the production dry-run will now show:

Before (broken): Mounts (0) → [DRY-RUN] would run: docker run ... → false safety signal.

After (fail-closed): Mounts (0) → [ABORT] no safe html source found. → [ABORT] No destructive action would be taken.

The three-option safety chain (_select_html_source):

A — existing bind to /usr/share/nginx/html with valid index.html that isn't nginx default
B — host artifact at /opt/clients/<container>/dist or build
C — docker cp from the running container before any docker stop/rm (live mode only; dry-run always aborts if A/B fail)
--force cannot bypass A/B/C — the html source check runs before the force check.

Production procedure (unchanged from before):


# Must show ABORT for affected containers, never "would run docker run"
python scripts/backfill_forwardauth.py --dry-run

# Only proceed after dry-run is clean on a throwaway hosting
python scripts/backfill_forwardauth.py --hosting-id <test_id>

---

## 2026-05-12 — Phase 3A: AI Action Recommendations con aprobación humana

### Restricciones permanentes de esta fase

En esta fase está prohibido:
- Ejecutar comandos, reiniciar contenedores, bloquear IPs
- Modificar Protection Mode, DNS, docker-compose
- Borrar archivos o eliminar containers
- Resolver incidentes automáticamente
- Cualquier escritura a DB salvo INSERT/UPDATE en `action_recommendations`

`execution_allowed` y `can_execute` son SIEMPRE false. Sin botón Ejecutar en ningún lugar.

---

### BLOQUE 1 — Migraciones (`app/infra/migrations.py`)

Añadidas al final de `_MIGRATIONS_PG`:

```sql
ALTER TABLE action_recommendations ADD COLUMN IF NOT EXISTS diagnosis_id BIGINT REFERENCES ai_diagnosis(id) ON DELETE SET NULL
ALTER TABLE action_recommendations ADD COLUMN IF NOT EXISTS source_type TEXT
ALTER TABLE action_recommendations ADD COLUMN IF NOT EXISTS incident_type TEXT
ALTER TABLE action_recommendations ADD COLUMN IF NOT EXISTS recommendation_source TEXT NOT NULL DEFAULT 'rule_based'
ALTER TABLE action_recommendations ADD COLUMN IF NOT EXISTS confidence REAL
ALTER TABLE action_recommendations ADD COLUMN IF NOT EXISTS reason TEXT
ALTER TABLE action_recommendations ADD COLUMN IF NOT EXISTS expected_impact TEXT
ALTER TABLE action_recommendations ADD COLUMN IF NOT EXISTS rollback_notes TEXT
ALTER TABLE action_recommendations ADD COLUMN IF NOT EXISTS safety_notes TEXT
ALTER TABLE action_recommendations ADD COLUMN IF NOT EXISTS payload JSONB DEFAULT '{}'
ALTER TABLE action_recommendations ADD COLUMN IF NOT EXISTS context_hash TEXT
ALTER TABLE action_recommendations ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()
CREATE INDEX IF NOT EXISTS idx_action_recs_diagnosis ON action_recommendations(diagnosis_id) WHERE diagnosis_id IS NOT NULL
CREATE INDEX IF NOT EXISTS idx_action_recs_risk ON action_recommendations(risk_level, created_at DESC)
CREATE INDEX IF NOT EXISTS idx_action_recs_hash ON action_recommendations(context_hash) WHERE context_hash IS NOT NULL
```

---

### BLOQUE 2 — `app/services/ai/action_safety_classifier.py` (nuevo)

Clasificador puro de riesgo por `action_type`. Cuatro niveles:
- `_POLICY_BLOCKED`: delete_container, delete_files, modify_dns, drop_database, force_restart_container, modify_docker_compose, resolve_incident_auto
- `_LOW_RISK`: customer_fix, monitor, manual_check, dependency_fix, branch_correction, site_recovery_monitor
- `_MEDIUM_RISK`: admin_review, security_review, enable_protection_mode_monitor, notify_customer, check_credentials
- `_HIGH_RISK`: block_ip_candidate, enable_protection_mode_protect, redeploy_candidate, restart_container_suggestion, escalate_to_admin

`classify_action(action_type) → SafetyResult`:
- `execution_allowed` SIEMPRE False
- `requires_approval` SIEMPRE True
- `blocked_by_policy=True` para tipos en `_POLICY_BLOCKED`

---

### BLOQUE 3 — `app/services/ai/action_recommendations.py` (nuevo, reescrito en 3A.1)

**Estructuras clave:**

`_OWNER_MAP`: mapeo `action_type → "cliente" | "admin" | "seguridad"`. Derivado por `_derive_owner(action_type)`. Default `"admin"`.

`_RULES`: dict `incident_type → list[dict]` con 8 tipos de incidente. Copy evita verbos de auto-ejecución. Cada entrada tiene `action_type`, `title`, `description`, `safety_notes`.

`_enrich(row) → dict`: añade `owner`, `owner_label`, `can_approve`, `can_reject`, `can_execute=False`, `execution_allowed=False`. `can_execute` nunca se almacena en DB, siempre derivado.

`_log_audit_event(action_id, incident_id, diagnosis_id, actor_user_id, previous_status, new_status)`: llama `activity_service.log_event` con `event_type=f"action_recommendation_{new_status}"`. Fallo no bloquea la operación.

`approve_action(conn, action_id, admin_user_id)`: UPDATE SET status=approved, `executed_at` permanece NULL siempre.

`reject_action(conn, action_id, admin_user_id, reason=None)`: SELECT status (captura `previous_status`), luego UPDATE.

**Idempotencia:** SHA-256 de `incident_id:diagnosis_id:action_type:context_hash` truncado a 32 chars. Si ya existe en DB, salta a menos que `force=True`.

**Copy de `github_private_repo_unauthorized`:**
- Título: "Verificar acceso al repositorio GitHub"
- Description: cubre URL inexistente / privado / sin permisos; no menciona token como única causa
- Safety notes: no modifica repositorio ni ejecuta comandos

---

### BLOQUE 4 — `app/api/routes/admin.py` (4 endpoints añadidos)

```
GET  /incidents/{incident_id}/actions         — lista acciones enriquecidas
POST /incidents/{incident_id}/actions/generate — genera en background (force: bool=False)
POST /actions/{action_id}/approve             — aprueba (audit log)
POST /actions/{action_id}/reject              — rechaza con reason opcional
```

`_RejectBody(reason: Optional[str] = Field(None, max_length=500))`

`generate_for_incident` usa `BackgroundTasks` de FastAPI; `LATERAL JOIN` para obtener último `ai_diagnosis` por incidente.

---

### BLOQUE 5 — `frontend/src/services/api.js` (añadido)

```javascript
getIncidentActions(incidentId)
generateActions(incidentId, force = false)
approveAction(actionId)
rejectAction(actionId, reason = null)
```

---

### BLOQUE 6 — `frontend/src/components/admin/SentinelPanel.jsx` (actualizado en 3A.1)

**Constantes nuevas:**
- `RISK_CLASS/RISK_LABEL/RISK_TOOLTIP`: Bajo/Medio/Alto/Crítico
- `STATUS_LABEL`: "Pendiente de revisión" / "Aprobada, no ejecutada" / "Rechazada" / "Reemplazada" / "Bloqueada por política"
- `STATUS_CLASS`: colores por estado

**`ActionsPanel` cambios clave:**
- `confirmId`: estado para aprobación en dos pasos (click Aprobar → dialog → Confirmar)
- `onActionsLoaded` prop: notifica al padre con items para incluir en copy report
- `data-testid="phase-notice"`: aviso persistente "aprobar solo registra la decisión, no ejecuta comandos"
- `data-testid="risk-badge"`: etiqueta de riesgo en español
- `data-testid="owner-label"`: "Responsable: Cliente/Admin/Seguridad"
- `data-testid="approved-notice"`: aparece en acciones aprobadas — explica no-ejecución automática
- `data-testid="blocked-notice"`: para `blocked_by_policy`
- Botones Aprobar/Rechazar ocultos en estados approved/rejected/blocked

**`buildReport(inc, diag, actions=[])` actualizado:**
- Sección ACCIONES RECOMENDADAS con title/owner/risk/status para cada acción no bloqueada
- Nota final: "HostingGuard no ejecutó cambios sobre tu sitio ni repositorio."
- Filtra acciones `blocked_by_policy`

**`IncidentRow`:**
- Estado `currentActions`
- Pasa `onActionsLoaded={setCurrentActions}` a ActionsPanel
- Pasa `currentActions` a `buildReport`

---

### BLOQUE 7 — Tests

**Backend `tests/test_action_recommendations.py` — 58 tests:**
- `TestActionSafetyClassifier`: risk levels, execution_allowed=False always, blocked_by_policy
- `TestGenerateActions`: generación, idempotencia, force override
- `TestApproveRejectAction`: approve/reject, executed_at siempre NULL
- `TestOwnerDerivation`: 7 tests para `_derive_owner`
- `TestEnrichRow`: 10 tests — can_execute=False always, can_approve/can_reject por status
- `TestCopyCorrectness`: 7 tests — no verbos de auto-ejecución, github title correcto, no policy-blocked en rules

**Frontend `SentinelPanel.test.jsx` — 35 tests:**
- Phase notice visible
- Risk badge en español ("Bajo" no "low")
- Owner label visible ("Cliente")
- Status label en español ("Pendiente de revisión")
- Two-step approve: click Aprobar → dialog → Confirmar → llama approveAction
- Approved state: "Aprobada, no ejecutada" + approved-notice
- Approved: oculta botón Aprobar
- Rejected: oculta ambos botones
- blocked_by_policy: blocked-notice visible
- Sin botón Ejecutar en ningún lugar
- github_private_repo description cubre más que solo token

---

### Estado de tests al cierre

- **Backend**: 58 tests en `test_action_recommendations.py`, todos verdes
- **Frontend**: 35 tests en `SentinelPanel.test.jsx`, todos verdes

### Pendiente producción

```sql
-- Tras deploy, verificar:
SELECT action_id, status, approved_at, executed_at
FROM action_recommendations ORDER BY created_at DESC LIMIT 10;
-- Esperado: approved_at NOT NULL cuando status='approved', executed_at siempre NULL

SELECT * FROM action_recommendations WHERE executed_at IS NOT NULL;
-- Esperado: 0 rows

-- Regenerar acciones para incident_id=38:
-- Título debe ser "Verificar acceso al repositorio GitHub"
-- No debe aparecer "Revisar permisos del token GitHub"
```

---

## 2026-05-12 — Fase 3B: Execution Planner + Fix 2 + Fase 3B.1

### Restricciones permanentes (siguen en vigor)

`execution_allowed` SIEMPRE false. Sin endpoint `/execute`. Sin botón Ejecutar.  
No se ejecuta nada. No se toca Docker, Traefik, DNS, contenedores, ni infraestructura.  
Solo INSERT/UPDATE en `execution_plans` y `action_audit_log`.

---

### Fase 3B — Execution Planner (base)

#### `app/infra/migrations.py`

Tabla `execution_plans`:
```sql
plan_id BIGSERIAL PRIMARY KEY
action_id BIGINT NOT NULL REFERENCES action_recommendations(action_id)
incident_id BIGINT, diagnosis_id BIGINT
plan_type TEXT NOT NULL
status TEXT NOT NULL DEFAULT 'draft'  -- draft | ready_for_review | blocked_by_policy | superseded | cancelled
risk_level TEXT NOT NULL DEFAULT 'low'
execution_allowed BOOLEAN NOT NULL DEFAULT FALSE   -- SIEMPRE false
requires_final_approval BOOLEAN NOT NULL DEFAULT TRUE
title TEXT, summary TEXT
prechecks JSONB DEFAULT '[]', steps JSONB DEFAULT '[]', rollback_steps JSONB DEFAULT '[]'
expected_impact TEXT, safety_notes TEXT, blocked_reason TEXT
planner_version TEXT, context_hash TEXT
created_by TEXT DEFAULT 'admin', created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW()
```

Tabla `execution_plan_audit_log`:
```sql
log_id BIGSERIAL PRIMARY KEY
plan_id BIGINT, action_id BIGINT, incident_id BIGINT, diagnosis_id BIGINT
actor TEXT, event TEXT NOT NULL  -- created | cancelled | superseded
details JSONB DEFAULT '{}'
created_at TIMESTAMPTZ DEFAULT NOW()
```

#### `app/services/ai/execution_plan_safety.py` (nuevo)

Clasificador puro de riesgo por `action_type` para planes de ejecución. Mismos 4 niveles que el clasificador de acciones. `execution_allowed` SIEMPRE false. `requires_final_approval` SIEMPRE true.

#### `app/services/ai/execution_planner.py` (nuevo, ~300 líneas)

**17 templates genéricos** (uno por `action_type`) + **2 templates específicos** (`(action_type, incident_type)`):
- `("customer_fix", "github_private_repo_unauthorized")` → `github_access_review` (status `ready_for_review`)
- `("dependency_fix", "node_sass_incompatible")` → `node_sass_migration` (status `ready_for_review`)

Cada template tiene: `title`, `summary`, `prechecks[]`, `steps[]`, `rollback_steps[]`, `safety_notes`, `plan_type`.

**`_plan_idempotency_hash(action_id, incident_id, diagnosis_id, action_type, action_context_hash, planner_version, incident_type)`** — SHA-256 de todos los campos concatenados con `:`. `incident_type` incluido desde el inicio para que templates específicos no colisionen con genéricos.

**`_existing_plan_hash(conn, action_id)`** — busca plan activo (excluye `cancelled` y `superseded`) y retorna su `context_hash`.

**`create_execution_plan(conn, action_id, force=False, actor="admin")`**:
1. Verifica acción `approved`
2. Clasifica riesgo (`blocked` → ValueError)
3. Selecciona template específico o genérico
4. Calcula hash del plan
5. Si hash igual y no force → retorno idempotente del plan existente
6. Si hash distinto O force → supersede/cancela plan activo:
   - Hash mismatch → `status=superseded` (automático, template mejorado)
   - `force=True` → `status=cancelled` (usuario explícito)
   - Captura `plan_id` via `RETURNING plan_id` para audit
7. Inserta nuevo plan con `execution_allowed=False`
8. Emite audit `created`; si supersedió emite audit `superseded` (no si canceló por force)

#### `app/api/routes/admin.py` — 4 endpoints nuevos

```
POST /actions/{action_id}/plan            — genera plan (force: bool = False)
GET  /actions/{action_id}/plans           — lista todos los planes de una acción
DELETE /plans/{plan_id}                   — cancela plan activo
GET  /incidents/{incident_id}/plans       — lista planes de todos los actions de un incidente
```

#### Frontend `SentinelPanel.jsx` (base 3B)

- `PlanCard` component: título, estado, riesgo, `plan-no-execute-notice`, prechecks/steps/rollback colapsables, `cancel-plan-btn` (solo si no cancelled/superseded), no hay botón Ejecutar
- `handleGeneratePlan(actionId, force)` — llama `generateActionPlan` + GET refresh desde DB
- `handleCancelPlan(planId, actionId)` — llama `cancelPlan` + GET refresh
- `hasPlan = !!(isApproved && existingPlan && !INACTIVE.includes(existingPlan.status))`
- Generate button: "Generar plan" (no plan) o "Regenerar plan" (hasPlan), onClick pasa `hasPlan` como force

#### Tests base 3B

- **Backend**: 50 tests en `tests/test_execution_planner.py` — safety classifier (13), create plan (12), idempotencia, templates genéricos/específicos, no subprocess/docker, audit logging
- **Frontend**: 67 tests en `SentinelPanel.test.jsx` — plan button visibility, generation, PlanCard fields, cancel, refresh from DB, current/historical grouping

---

### Fase 3B Fix 2 — Persistencia de planes y agrupación current/historical

**Problema 1 — Plan específico no persiste:**  
`_plan_idempotency_hash` no incluía `incident_type`. Plan específico (`github_private_repo`) calculaba el mismo hash que el genérico previo → retorno idempotente del plan genérico stale.  
**Fix:** `incident_type` ya estaba en la firma pero no se incluía en el string SHA-256. Añadido.

**Problema 2 — Plan se generaba en action_id incorrecto (v1 en lugar de v2):**  
Con dos acciones del mismo `action_type`, la v1 (stale) aparecía como current action. El usuario veía su plan cargado en la v1.  
**Fix:** Actions agrupadas como current/historical — sorted `created_at DESC`, primera por `action_type` = current (tarjeta visible), resto = historical (sección colapsable "Versiones anteriores").

**Cambios en `execution_planner.py`:**
- `create_execution_plan`: separación cancel/supersede. Hash mismatch → `superseded` siempre (independiente de `force`); `force=True` → `cancelled`. Ambos usan `RETURNING plan_id` para audit.

**Cambios en `SentinelPanel.jsx`:**
- `currentActions` / `historicalActions` via `useMemo`: sort DESC + Set de `action_type` vistos
- `hasPlan` envuelto en `!!()` → garantiza booleano (evita `generateActionPlan(id, null)`)
- `handleGeneratePlan`: GET refresh después de generate (nunca confía en estado local)
- `handleCancelPlan`: GET refresh después de cancel
- `cancel-plan-btn`: oculto para `cancelled` y `superseded`

**Tests nuevos:**
- Backend: `test_incident_type_changes_hash`, `test_hash_mismatch_auto_supersedes_without_force`, `TestExistingPlanHash` (2 tests), mocks corregidos (`cancel_cur.fetchone.return_value = {"plan_id": 99}`)
- Frontend: 4 tests current/historical, 3 tests plan refresh from DB, fix mock ordering

---

### Fase 3B.1 — Auditoría, enriquecimiento API, copiar plan, planes anteriores

#### Backend — `execution_planner.py`

- `create_execution_plan`: cuando supersede por hash mismatch, emite `execution_plan_superseded` via `_log_plan_audit` para el plan antiguo (adicional al `created` del nuevo). `force=True` no emite `superseded` (es cancelación explícita del usuario).

#### Backend — `admin.py`

Constantes nuevas:
```python
_PLAN_STATUS_LABEL = { "draft": "Borrador", "ready_for_review": "Listo para revisión", "blocked_by_policy": "Bloqueado por política", "superseded": "Reemplazado", "cancelled": "Cancelado" }
_PLAN_RISK_LABEL   = { "low": "Bajo", "medium": "Medio", "high": "Alto", "critical": "Crítico" }
_PLAN_CAN_CANCEL_STATUSES = {"draft", "ready_for_review"}
_PLAN_INACTIVE_STATUSES   = {"cancelled", "superseded"}
```

`_enrich_plan(plan, *, is_current: bool) → dict`:
- Añade: `status_label`, `risk_label`, `execution_allowed_label` ("No permitido en esta fase"), `requires_final_approval_label`, `can_cancel` (bool), `can_copy` (siempre True), `is_current`, `is_historical`

`_enrich_plans(plans) → list[dict]`:
- Itera en `created_at DESC`. Primer plan no-inactivo → `is_current=True`, resto → `is_historical=True`.
- Aplicado a: `GET /actions/{id}/plans`, `GET /incidents/{id}/plans`, `POST /actions/{id}/plan`.

#### Backend — tests (`test_execution_planner.py`)

`TestEnrichPlan` (16 tests): `status_label` por cada estado, `risk_label`, `can_cancel=True` para draft/ready_for_review, `can_cancel=False` para cancelled/superseded, `is_current`/`is_historical`, `execution_allowed_label`, `can_copy`, campos originales preservados.

`TestEnrichPlans` (4 tests): primer no-inactivo = current, todos inactivos = todos historical, solo el primero activo = current, lista vacía.

`TestAuditSuperseded` (3 tests): `superseded` audit event en hash mismatch, `force=True` NO emite `superseded`, audit failure no crashea create.

**Total backend: 72 tests (era 50).**

#### Frontend — `SentinelPanel.jsx`

**`buildPlanReport(plan, { incidentTitle, actionTitle, incidentType })`** — función pura, texto humano legible:
- Sin JSON, sin objetos raw
- Secciones: incidente, acción aprobada, título/estado/riesgo, permitido ejecutar = No, resumen, prechecks, pasos, rollback, notas de seguridad
- Siempre termina con: "Aprobar o generar este plan no ejecuta cambios sobre HostingGuard, Docker, Traefik, DNS ni el repositorio del cliente."

**`buildReport(inc, diag, actions, activePlansMap)`** — 4to param añadido:
- Por cada acción aprobada con plan activo: título del plan, estado, "Ejecución permitida: No", prechecks, pasos
- Nota de seguridad al final: "HostingGuard no ejecutó cambios automáticamente."

**`plansMap`** ahora almacena `allPlans[]` por `action_id` (antes `activePlan|null`).  
Al renderizar: `existingPlan = allPlans.find(active)`, `historyPlans = allPlans.filter(inactive)`.

**`handleGeneratePlan`**: guarda array completo + llama `onPlansLoaded({ [actionId]: active })` para actualización parcial de `currentPlansMap` en IncidentRow.

**`handleCancelPlan`**: guarda array completo + `setCancelSuccessActionId(actionId)` con auto-clear 4s + llama `onPlansLoaded({ [actionId]: active | undefined })`.

**Cancel success message**: `<p data-testid="cancel-success-msg">Plan cancelado. No se ejecutó ninguna acción.</p>` por acción.

**`PlanCard`** — nuevas props: `historyPlans`, `actionTitle`, `incidentTitle`, `incidentType`.
- "Copiar plan" button (`data-testid="copy-plan-btn"`): llama `buildPlanReport`, escribe a clipboard, feedback "Copiado" 2s
- Cancel button: usa `plan.can_cancel ?? !['cancelled','superseded'].includes(plan.status)`
- "Planes anteriores" collapsible (`data-testid="history-plans-toggle"`, `history-plans-list`): lista planes cancelados/superseded con título, `status_label`, fecha formateada

**`IncidentRow`**:
- `currentPlansMap` state (vacío hasta que `onPlansLoaded` sea llamado desde ActionsPanel)
- `onPlansLoaded={updates => setCurrentPlansMap(prev => ({...prev, ...updates}))}` → merge parcial
- Pasa `incidentTitle={inc.title}`, `incidentType={inc.incident_type}` a ActionsPanel
- `handleCopy` pasa `currentPlansMap` como 4to arg a `buildReport`

**`ActionsPanel`** nuevas props: `incidentTitle`, `incidentType` (pasadas a PlanCard).

#### Frontend — tests nuevos (`SentinelPanel.test.jsx`)

Phase 3B.1 — PlanCard copy plan (4): botón visible, llama clipboard, texto incluye disclaimer, texto sin JSON raw.  
Phase 3B.1 — PlanCard can_cancel (2): `can_cancel=false` oculta botón, `can_cancel=true` lo muestra.  
Phase 3B.1 — cancel success message (1): mensaje "Plan cancelado. No se ejecutó ninguna acción." tras cancelar.  
Phase 3B.1 — history plans in PlanCard (3): toggle visible con historial, plan cancelado en lista tras click, no toggle cuando solo un plan.  
Phase 3B.1 — Copiar informe includes plan (3): nota de seguridad, título del plan en informe, "Ejecución permitida: No".

**Total frontend: 80 tests (era 67).**

#### Verificación en producción (pendiente)

```sql
-- Confirmar plan activo para incident_id=38 / action_id=3
SELECT plan_id, status, plan_type, title, created_at
FROM execution_plans WHERE action_id = 3 ORDER BY created_at DESC;

-- Confirmar audit events
SELECT event, plan_id, created_at FROM execution_plan_audit_log
WHERE action_id = 3 ORDER BY created_at DESC;

-- execution_allowed siempre false
SELECT COUNT(*) FROM execution_plans WHERE execution_allowed = TRUE;
-- Esperado: 0
```

---

## 2026-05-14 — NPM Supply-Chain Guard (TanStack) + Package Manager Detection + Build Secret Isolation

### Contexto

El 2026-05-11 se reveló un compromiso de cadena de suministro npm que afectó 10 paquetes `@tanstack/*`. Se implementó un guard preventivo en el preflight del deploy que escanea lockfiles antes de ejecutar `npm install`, bloqueando cualquier proyecto que referencie versiones comprometidas. En paralelo, se extendió el deploy service para soportar pnpm y yarn nativamente vía corepack, se reforzó el guard de package manager (lockfile requerido, múltiples lockfiles detectados), y se aisló la ejecución de builds de secretos de producción.

---

### BLOQUE 1 — Supply-chain guard: TanStack

**Archivo**: `app/services/deploy/dependency_preflight.py`

`_TANSTACK_AFFECTED` — dict con las 10 versiones comprometidas:
```python
_TANSTACK_AFFECTED = {
    "@tanstack/react-query":        {"5.75.0", "5.75.1"},
    "@tanstack/query-core":         {"5.75.0", "5.75.1"},
    "@tanstack/react-table":        {"8.21.0"},
    "@tanstack/table-core":         {"8.21.0"},
    "@tanstack/react-virtual":      {"3.13.0"},
    "@tanstack/virtual-core":       {"3.13.0"},
    "@tanstack/react-router":       {"1.114.0"},
    "@tanstack/router-core":        {"1.114.0"},
    "@tanstack/start":              {"1.114.0"},
    "@tanstack/react-form":         {"1.0.0"},
}
```

**Scanners de lockfile** (todos retornan `dict[pkg_name, version]` de los `@tanstack/*` encontrados):

- `_scan_npm_lockfile_format(path)` — helper compartido para package-lock.json y npm-shrinkwrap.json. Soporta formato v1 (`dependencies`), v2/v3 (`packages`, con paths anidados tipo `node_modules/@scope/pkg`). Extrae el nombre real del paquete con `split("node_modules/")[-1]`.
- `_scan_package_lock(work_dir)` → llama `_scan_npm_lockfile_format` con `package-lock.json`
- `_scan_shrinkwrap(work_dir)` → llama `_scan_npm_lockfile_format` con `npm-shrinkwrap.json`
- `_scan_pnpm_lock(work_dir)` → regex `r"""['"/ ](@tanstack/[\w-]+)@([\d]+\.[\d]+\.[\d]+[\w.-]*)['"/ ]?\s*:"""` sobre el YAML como texto plano
- `_scan_yarn_lock(work_dir)` → parser línea a línea; soporta yarn classic v1 (sección `"@pkg@ver":`) y berry (`"@pkg@npm:ver":`)

`_tanstack_supply_chain_check(work_dir, pkg)`:
1. Recopila versiones afectadas escaneando los 4 lockfiles (package-lock, shrinkwrap, pnpm, yarn)
2. Si `affected_packages` no vacío → retorna `DeployError` con code `npm_supply_chain_tanstack_compromise`, `evidence.affected_packages`
3. Si no hay lockfile pero `@tanstack/*` en `pkg.dependencies/devDependencies` → retorna `npm_lockfile_required_for_supply_chain_safety`
4. `has_lock`: considera `package-lock.json`, `npm-shrinkwrap.json`, `pnpm-lock.yaml`, `yarn.lock`

**Prioridad en `run_dependency_preflight`**:
1. node-sass check
2. TanStack supply-chain check ← nuevo (antes del PM check)
3. Package manager check
4. Node version check
5. Next.js SSR check

---

### BLOQUE 2 — Build container secret isolation

**Archivo**: `app/services/deploy/build_runner.py`

`_BLOCKED_BUILD_ENV_RE` — regex compilado `re.IGNORECASE`:
```python
_BLOCKED_BUILD_ENV_RE = re.compile(
    r"DATABASE_URL$|DB_PASS|DB_PASSWORD|SECRET_KEY|JWT_SECRET"
    r"|NPM_TOKEN|NODE_AUTH_TOKEN|GITHUB_TOKEN|GH_TOKEN"
    r"|SSH_PRIVATE_KEY|SSH_KEY(?:$|_)|PRIVATE_KEY|API_SECRET",
    re.IGNORECASE,
)
```

`_safe_build_env_flags(env_vars: dict) -> list[str]`:
- Filtra `env_vars` eliminando toda key que coincida con `_BLOCKED_BUILD_ENV_RE`
- Llama `_docker_env_flags` con el dict filtrado
- Retorna `[]` si `env_vars` vacío

Variables bloqueadas: `DATABASE_URL`, `DB_PASS`, `DB_PASSWORD`, `SECRET_KEY`, `JWT_SECRET`, `NPM_TOKEN`, `NODE_AUTH_TOKEN`, `GITHUB_TOKEN`, `GH_TOKEN`, `SSH_PRIVATE_KEY`, `SSH_KEY*`, `PRIVATE_KEY`, `MY_PRIVATE_KEY`, `API_SECRET`.

Variables seguras (pasan): `NODE_ENV`, `VITE_*`, `REACT_APP_*`, `PUBLIC_URL`.

En `github_deploy_service.py`: `_env_flags = _safe_build_env_flags(data.env_vars)` reemplaza llamada directa a `_docker_env_flags`.

---

### BLOQUE 3 — Package manager detection + lockfile guard

**Archivo**: `app/services/deploy/dependency_preflight.py`

Reescritura de `_package_manager_check(work_dir)`:
```python
has_npm  = (os.path.exists(".../package-lock.json")
            or os.path.exists(".../npm-shrinkwrap.json"))
has_pnpm = os.path.exists(".../pnpm-lock.yaml")
has_yarn = os.path.exists(".../yarn.lock")
lockfile_count = sum([has_npm, has_pnpm, has_yarn])

if lockfile_count > 1:
    → multiple_lockfiles_detected
      evidence: {"lockfiles": [...], "install_skipped": True}

if lockfile_count == 0:
    → lockfile_required
      evidence: {"install_skipped": True}

return None  # single lockfile = pass
```

Nueva función `_extract_pm_version(pm_field, pm_name)`:
- Parsea `"pnpm@8.15.4"` o `"yarn@4.1.0+sha256.abc"` → extrae solo `X.Y.Z`
- Si el campo pertenece a otro PM → retorna `None`

Nueva función `detect_package_manager(work_dir, pkg) -> dict`:
- Prioridad: pnpm-lock.yaml > yarn.lock > package-lock.json > npm-shrinkwrap.json
- Lee `pkg.get("packageManager", "")` para versión pinneada (corepack)
- Retorna `{"package_manager": str, "lockfile": str, "version": str|None}`

`_package_manager_check` ya **no bloquea** pnpm ni yarn (son PMs válidos). Solo bloquea múltiples lockfiles o ausencia de lockfile.

---

### BLOQUE 4 — Build orchestration: pnpm/yarn/npm via corepack

**Archivo**: `app/services/deploy/github_deploy_service.py`

Flujo en `has_package_json` block:
1. Detección de framework y `out_dir` (sin install_cmd/build_cmd aún)
2. `run_dependency_preflight(work_dir, pkg)` → `raise DeployError` si falla
3. `_pm_info = detect_package_manager(work_dir, pkg)` → `_pm = _pm_info["package_manager"]`
4. Asignación de comandos según `_pm`:

```python
if _pm == "pnpm":
    ver = _pm_info["version"]
    corepack_prepare = f"corepack prepare pnpm@{ver} --activate" if ver else "corepack prepare pnpm --activate"
    install_cmd = f"corepack enable && {corepack_prepare} && pnpm install --frozen-lockfile"
    build_cmd   = f"pnpm run build"
elif _pm == "yarn":
    install_cmd = "corepack enable && yarn install --immutable"
    build_cmd   = "yarn build"
else:  # npm
    install_cmd = "npm ci"
    build_cmd   = "npm run build"
```

5. `deploy_log["stages"]["build_info"]["package_manager"] = _pm`

**ERESOLVE retry**: guard `if _pm == "npm" and "ERESOLVE" in _iout:` — evita retry incorrecto en pnpm/yarn.

**PM-specific failure codes**: si `classify_npm_failure` retorna `npm_install_failed`, se mapea a:
```python
_icode = {"pnpm": "pnpm_install_failed", "yarn": "yarn_install_failed"}.get(_pm, "npm_ci_failed")
```

---

### BLOQUE 5 — Diagnostics matrix + Frontend

**Archivo**: `app/services/deploy/diagnostics_matrix.py`

Códigos nuevos agregados:

| Código | Stage | Severity | Retryable |
|--------|-------|----------|-----------|
| `multiple_lockfiles_detected` | dependency_preflight | error | False |
| `lockfile_required` | dependency_preflight | warning | False |
| `npm_supply_chain_tanstack_compromise` | dependency_preflight | critical | False |
| `npm_lockfile_required_for_supply_chain_safety` | dependency_preflight | critical | False |
| `npm_supply_chain_risk` | dependency_preflight | critical | False |
| `npm_ci_failed` | dependency_install | warning | True |
| `pnpm_install_failed` | dependency_install | warning | True |
| `yarn_install_failed` | dependency_install | warning | True |

`package_manager_pnpm_detected` y `package_manager_yarn_detected` — mantenidos con descripción "(legacy)" para compatibilidad histórica; `retryable: True`.

**Archivo**: `frontend/src/components/deploy/DeployDiagnosticCard.jsx`

- 8 nuevos `CODE_LABELS` (supply-chain, lockfile, PM-specific)
- `SUPPLY_CHAIN_CODES = new Set(["npm_supply_chain_tanstack_compromise", "npm_lockfile_required_for_supply_chain_safety", "npm_supply_chain_risk"])`
- Banner rojo de seguridad para `isSupplyChain`: `ShieldAlert` + texto explicativo del compromiso TanStack
- Panel de paquetes comprometidos: `evidence.affected_packages` → lista `pkg@version` en rojo/naranja
- Banner ámbar de `install_skipped` sin cambios

---

### BLOQUE 6 — Tests

**`tests/test_tanstack_supply_chain.py`** (nuevo, 23 tests):
- Detección en package-lock.json v2/v3 (nested `node_modules/` path)
- Detección en package-lock.json v1 (`dependencies` field)
- Detección en npm-shrinkwrap.json
- Detección en pnpm-lock.yaml
- Detección en yarn.lock v1 y berry
- Versión no comprometida → `None`
- Paquete @tanstack sin lockfile → `npm_lockfile_required_for_supply_chain_safety`
- `@tanstack/*` sin lockfile pero fuera de deps → no bloquea
- Supply-chain tiene prioridad sobre node-sass y node version
- Múltiples paquetes comprometidos detectados simultáneamente

**`tests/test_package_manager_detection.py`** (nuevo, 37 tests):
- `detect_package_manager`: pnpm/npm/yarn/shrinkwrap, version extraction desde `packageManager` field, version `None` si field pertenece a otro PM
- `_package_manager_check`: single lockfile pasa (pnpm/npm/yarn/shrinkwrap), múltiples lockfiles bloquea (todas combinaciones), sin lockfile bloquea
- `run_dependency_preflight` integración: pnpm lockfile pasa, npm pasa, múltiples bloquea, sin lockfile bloquea
- Supply-chain tiene prioridad sobre `lockfile_required` (pnpm-lock.yaml con @tanstack comprometido → supply-chain code, no lockfile_required)
- `_scan_shrinkwrap`: missing → `{}`, compromised → `{"@tanstack/react-query": "5.75.0"}`
- `_safe_build_env_flags`: strips DATABASE_URL, NPM_TOKEN, GITHUB_TOKEN, GH_TOKEN, SSH_PRIVATE_KEY, SSH_KEY, JWT_SECRET, DB_PASSWORD, DB_PASS, PRIVATE_KEY, NODE_AUTH_TOKEN, API_SECRET; safe vars (NODE_ENV, VITE_*, REACT_APP_*) pasan; input vacío → `[]`

**`tests/test_diagnostics_matrix.py`** — actualizaciones:
- `test_yarn_lock_detected`: ahora `assert result is None` (yarn soportado)
- `test_pnpm_lock_detected`: ahora `assert result is None` (pnpm soportado)
- `test_yarn_lock_with_package_lock_not_blocked`: ahora `assert result["code"] == "multiple_lockfiles_detected"`
- `test_engines_node_upper_bound_incompatible`, `test_engines_node_open_upper_bound_ok`: temp dir incluye `package-lock.json` para no triggear `lockfile_required` antes del check de node version

**Fixtures actualizadas** — agregado `package-lock.json` mínimo (`{"lockfileVersion": 3, "packages": {}}`) a:
- `tests/fixtures/github_repos/node_version_nvmrc/`
- `tests/fixtures/github_repos/vite_clean/`
- `tests/fixtures/github_repos/next_ssr/`
- `tests/fixtures/github_repos/next_static_export/`

**Total tests**: 977 pasando (0 failed).

---

## 2026-05-14 — Fix Crítico: Routing Traefik para api.hostingguard.lat + Persistencia via Dynamic Files

### Contexto

Después de los últimos deploys, `api.hostingguard.lat/health` devolvía 404. El frontend cargaba correctamente (SPA fallback vía Nginx) pero todas las llamadas de API fallaban, haciendo el dashboard inutilizable. Diagnóstico: Traefik no tenía router activo para `api.hostingguard.lat` — la request no llegaba al contenedor `app`. App respondía internamente en `http://127.0.0.1:8000/health` sin problemas.

Causa raíz: el `docker-compose.yml` en `/opt/deploy/` (editado manualmente, nunca sincronizado con git) tenía labels de Traefik para el router `hg` que no estaban siendo aplicadas correctamente — probablemente divergencia entre el repo y producción. Solución inmediata: dynamic files en `/opt/traefik-dynamic/` que Traefik recarga automáticamente sin reiniciar contenedores.

---

### BLOQUE 1 — Fix inmediato (ya aplicado en producción)

Archivos creados manualmente en el servidor:

**`/opt/traefik-dynamic/platform-frontend.yml`**:
- Router `platform-frontend`, rule `Host(\`hostingguard.lat\`) || Host(\`www.hostingguard.lat\`)`
- Service URL: `http://frontend:80`
- TLS certResolver `le`
- Sin ForwardAuth

**`/opt/traefik-dynamic/platform-api.yml`**:
- Router `platform-api`, rule `Host(\`api.hostingguard.lat\`)`
- Service URL: `http://hosting_guard:8000`, flushInterval 100ms
- TLS certResolver `le`
- Sin ForwardAuth (FastAPI maneja JWT internamente — agregar ForwardAuth causaría loop infinito)

Validación post-fix:
- `https://hostingguard.lat` → 200
- `https://hostingguard.lat/login` → 200
- `https://hostingguard.lat/dashboard` → 200
- `https://api.hostingguard.lat/health` → 200

---

### BLOQUE 2 — Persistencia: script idempotente

**Archivo**: `scripts/ensure_platform_traefik_routes.sh`

Script bash idempotente que:
1. Crea `/opt/traefik-dynamic/` si no existe
2. Escribe `platform-frontend.yml` y `platform-api.yml` con contenido canónico (siempre sobreescribe para garantizar consistencia)
3. Verifica que los contenedores `traefik`, `hosting_guard`, `frontend` estén corriendo
4. Chequea internamente que `http://127.0.0.1:8000/health` responda 200 dentro del contenedor app
5. Corre 4 checks públicos: `api.hostingguard.lat/health`, `hostingguard.lat/`, `/login`, `/dashboard`
6. Imprime `ALL OK — N checks passed` o `FAIL — N check(s) failed` con instrucciones de troubleshooting
7. Sale con `exit 1` si hay algún fallo (compatible con CI/deploy pipeline)
8. Acepta `--check-only` para verificar sin escribir archivos

Ambos routers tienen `priority: 100` — garantiza que los file provider routers ganen sobre cualquier label Docker con la misma regla (evita undefined behavior si hay duplicados).

---

### BLOQUE 3 — Runbook en ARCHITECTURE.md

Sección nueva agregada: **"Traefik Routing Runbook (updated 2026-05-14)"**

Documenta:
- Modelo de providers: Docker (middleware hg-forwardauth + service hg) vs File (platform routes + tenant routes)
- Por qué los platform routes viven en file provider (no en labels Docker): los labels se pierden si el contenedor se recrea antes de estar healthy
- Qué labels Docker del servicio `app` deben mantenerse (middleware + service, NO el router)
- Tabla de ForwardAuth scope: qué rutas lo necesitan y cuáles no (con el porqué)
- Runbook "API devuelve 404": 4 comandos de diagnóstico + restore con el script
- Runbook "deploy checklist": correr el script después de cualquier deploy que toque app/frontend/traefik
- Runbook "editar dynamic files de forma segura": backup → editar → validar YAML → Traefik auto-recarga

### Invariante de seguridad documentada

**NUNCA agregar `hg-forwardauth` a `api.hostingguard.lat`**: el endpoint `/internal/forwardauth` del app es el que valida las requests — si se le agrega ForwardAuth, cada request a la API llama a `/internal/forwardauth`, que también pasa por Traefik, que llama de nuevo a `/internal/forwardauth` → loop infinito. Esto está documentado en el runbook y en comentarios dentro de los YAML.

---

## 2026-05-14 — Fase 4A.2: Router Health Guard

**Objetivo**: Detectar automáticamente routing roto en Traefik (plataforma + tenants) antes de que afecte usuarios, con auto-reparación limitada a rutas de plataforma y creación de incidentes para tenants.

**Principio de seguridad**: Router Health Guard NO toca código del cliente, archivos del cliente, base de datos del cliente, DNS externo, Docker Compose global, certificados, datos sensibles, ni billing. Solo diagnóstica y repara rutas de plataforma propias.

### BLOQUE 1 — Servicio: `app/services/router_health_guard.py`

**`RouterHealthResult`** (dataclass):
- Campos: `host`, `scope` (platform|tenant), `hosting_id`, `container_name`, `container_running`, `router_source` (docker_labels|dynamic_file|unknown|none), `public_status_code` (-2=SSL error, -1=timeout, 0=conn refused, 1xx–5xx), `content_type`, `healthy`, `incident_type`, `summary`, `evidence`, `checked_at`
- `to_dict()` para serialización API

**`_http_check(url, timeout)`**: Hace HTTP GET con `urllib.request`, devuelve `(status_code, content_type, body_size)`. Detecta timeout (-1), SSL error (-2), connection error (0).

**`_classify_failure(status_code, ct, body_size)`**: Clasifica el fallo en `incident_type`:
- 404 + body 19 bytes + `text/plain` → `traefik_router_missing_or_unmatched`
- 404 otro → `app_level_404`
- 502/503 → `backend_unreachable`
- -1 → `timeout`
- -2 → `ssl_error`
- 0 → `connection_refused`
- Otro → `unexpected_status`

**`check_platform_routes()`**: Chequea los 3 hosts de plataforma (`hostingguard.lat`, `www.hostingguard.lat`, `api.hostingguard.lat`). Para cada uno:
- Determina `router_source` leyendo si existe el archivo dynamic file
- Hace HTTP check al URL público
- Si falla: emite incidente via `_emit_platform_incident`
- Devuelve lista de `RouterHealthResult`

**`check_tenant_routes(limit=100, hosting_id=None)`**: Consulta DB → `status='active'`, `subdomain NOT NULL`, `container_name NOT NULL`. Para cada tenant:
- Si contenedor no corre: `incident_type=container_stopped`, sin HTTP check
- Si corre: HTTP check a `https://{subdomain}.hostingguard.lat`
- `expected_statuses = [200, 301, 302, 401, 403]` (ForwardAuth devuelve 401/302 para no autenticados — es correcto)
- Si falla: emite incidente via `_emit_tenant_incident` (nunca auto-repara)
- Error por tenant aislado con try/except (un fallo no aborta el resto)

**`ensure_platform_traefik_routes(dry_run=False)`**: Compara contenido actual de los archivos dynamic con el YAML canónico embebido. Si difiere o no existe: hace backup del existente → escribe nuevo (solo si `dry_run=False`). Devuelve dict con `dry_run`, `changed`, `files` (path → action: created|updated|unchanged).

**`router_health_guard_job()`**: Corre en scheduler cada 60s (initial_delay=30s):
1. `check_platform_routes()` → si `REPAIR_MODE == "protect"` y hay fallos, llama `ensure_platform_traefik_routes()` y loguea resultado
2. `check_tenant_routes()` → loguea `tenant_router_repair_skipped_policy` por cada tenant unhealthy (nunca repara)

### BLOQUE 2 — Política de reparación: `app/services/router_repair_policy.py`

```python
REPAIR_MODE: str = os.getenv("ROUTER_HEALTH_REPAIR_MODE", "protect")
```

Modos: `off` (solo detecta), `monitor` (detecta + alerta sin reparar), `protect` (auto-repara solo plataforma). Default: `protect`.

Tenants: **nunca auto-reparar** — siempre solo diagnóstico + incidente.

### BLOQUE 3 — Incidentes: deduplicación por `correlation_key`

- Plataforma: `f"platform_route:{incident_type}:{host}"`
- Tenant: `_context_hash(host, hosting_id, incident_type, container_name)` — SHA256 truncado a 16 chars
- Upsert via `_upsert_incident` de `app.services.incidents.incident_deduper`
- Campos: `incident_type`, `severity`, `title`, `description`, `correlation_key`, `context_json`

### BLOQUE 4 — API Admin: `app/api/routes/admin_router_health.py`

Todos los endpoints protegidos con `Depends(require_role("admin"))`.

| Endpoint | Función |
|---|---|
| `GET /admin/router-health/platform` | Config estática + existencia de archivos (sin HTTP check) |
| `POST /admin/router-health/platform/check` | Ejecuta `check_platform_routes()` en tiempo real |
| `POST /admin/router-health/platform/repair` | Body `{"dry_run": bool}`, llama `ensure_platform_traefik_routes` |
| `GET /admin/router-health/tenants` | Params: `unhealthy_only`, `hosting_id`, `limit=50` |
| `POST /admin/router-health/tenants/check` | Param: `hosting_id` opcional |

Registrado en `app/api/main.py` via `app.include_router(router_health_router)`.

### BLOQUE 5 — UI: `frontend/src/components/admin/RouterHealthPanel.jsx`

Tab "Plataforma":
- Carga config estática de `GET /platform` al montar
- Botones: "Verificar ahora" (POST check), "Simular reparación" (POST repair dry_run=true), "Reparar rutas de plataforma" (POST repair dry_run=false, con `window.confirm`)
- Por cada ruta: badge de `router_source`, `dynamic_file_exists`, `public_status_code`, `incident_type`

Tab "Tenants":
- Carga de `GET /tenants`, filtro checkbox "Solo con problemas"
- Filas colapsables: info de Docker + status code
- Badge por `container_running`, `router_source`, `incident_type`

Navegación en `AdminDashboard.jsx`: ítem `{ id: 'router-health', label: 'Router Health', icon: Globe }`.

### BLOQUE 6 — Tests: `tests/test_router_health_guard.py`

22 tests cubriendo los 20 criterios de aceptación del spec + 2 adicionales:

- Tests 1–3: clasificación de fallos (`_classify_failure`)
- Tests 4–5: chequeo de rutas de plataforma (healthy y fallo Traefik 404)
- Tests 6–7: chequeo de tenants (contenedor parado, HTTP 401 es healthy)
- Tests 8–9: `ensure_platform_traefik_routes` (dry_run, repair efectivo)
- Test 10: `ensure_platform_traefik_routes` no escribe si ya está correcto (idempotencia)
- Tests 11–12: emisión de incidentes de plataforma y tenant
- Test 13: `_http_check` timeout → código -1
- Test 14: ForwardAuth no presente en YAMLs de plataforma (sin `middlewares:` ni `hg-forwardauth@`)
- Test 15: scheduler job llama `check_platform_routes` y `check_tenant_routes`
- Tests 16–17: respuesta estructurada de API (testeados via service functions directamente — dependency override de FastAPI no funciona con `require_role("admin")` factory)
- Tests 18–20: repair solo en mode "protect", `correlation_key` correcto, log de audit en repair
- Tests 21–22: SSL error → código -2, tenant con fallo no bloquea al siguiente

Resultado final: **22 passed**.

### Fix técnico relevante: patch path para `get_connection`

`get_connection` se importa dentro del cuerpo de `check_tenant_routes` (no a nivel de módulo). El patch correcto es `app.infra.db.get_connection`, no `app.services.router_health_guard.get_connection`.

---

## 2026-05-14 — Fase 4A.2 Fix: Falsos positivos en Plataforma y Tenants (BLOQUE 2)

### Problema

Cuatro falsos positivos reportados en producción tras desplegar el Router Health Guard:

1. **Tenant host duplicado**: `mi-academia.hostingguard.lat.hostingguard.lat` — la columna `subdomain` en DB almacena FQDNs completos; el código concatenaba `.hostingguard.lat` sin verificar.
2. **Plataforma marcada Unhealthy incorrectamente**: `/opt/traefik-dynamic/` no está montado en el container de la app (solo en el container de Traefik). `os.path.exists()` devuelve `False` aunque la ruta pública devuelva 200.
3. **`router_source=docker_labels` + "FALTANTE"**: Contradicción al mostrar en UI `router_source=docker_labels` (fuente correcta) con badge de archivo dinámico faltante — el archivo dinámico es irrelevante si la ruta viene de docker labels.
4. **Admin curl auth**: Comportamiento correcto — no tocar.

### Correcciones aplicadas

#### `app/services/router_health_guard.py`

**`normalize_tenant_public_host(subdomain, base_domain=_BASE_DOMAIN) -> str`** (nueva función):
- Elimina protocolo y path
- Si termina en `.hostingguard.lat` o ES el base domain → devuelve tal cual (evita duplicación)
- Si contiene `.` pero no es el dominio base → devuelve tal cual (dominio custom)
- Si no contiene `.` → añade `.hostingguard.lat`
- `_BASE_DOMAIN = "hostingguard.lat"` como constante de módulo

**`_dynamic_file_visibility(path: str) -> str`** (nueva función):
- `"visible"` — el archivo existe y es legible
- `"not_mounted_in_app"` — el directorio padre no existe: el volumen no está montado en este container
- `"absent"` — el directorio existe pero el archivo no (falta genuino)

**`RouterHealthResult` dataclass**:
- Campo nuevo: `dynamic_file_visibility: Optional[str] = None`
- `to_dict()` incluye `"dynamic_file_visibility": self.dynamic_file_visibility`

**`check_platform_routes()`**:
- Calcula `dfile_visibility = _dynamic_file_visibility(dfile)` en lugar de `os.path.exists(dfile)`
- Asigna `dynamic_file_visibility` al resultado
- La salud de la ruta de plataforma depende del HTTP check, no de la visibilidad del archivo

**`_check_tenant_hosting()`**:
- Usa `host = normalize_tenant_public_host(subdomain)` en lugar de `f"{subdomain}.hostingguard.lat"`

#### `app/api/routes/admin_router_health.py` — `GET /platform`

- Usa `_dynamic_file_visibility` en lugar de `os.path.exists`
- Campo renombrado: `dynamic_file_visibility` (antes `dynamic_file_exists`)
- Plataforma sana si HTTP check pasa, independientemente de visibilidad del archivo en este container

#### `frontend/src/components/admin/RouterHealthPanel.jsx` — `DynamicFileTag`

Nuevo componente contextual que muestra tres estados distintos:
- `"visible"` → badge azul "Archivo presente"
- `"not_mounted_in_app"` → badge gris "No montado (normal)" — no implica error
- `"absent"` → badge rojo "Archivo faltante" — sí implica error
- `null/undefined` → badge gris "Desconocido"

El badge "FALTANTE" ya no se muestra para rutas cuya fuente es `docker_labels` cuando el volumen no está montado en el container de la app.

### Tests añadidos (23–30)

- Tests 23–25: `normalize_tenant_public_host` — FQDN ya completo, bare slug, dominio con punto pero no base domain
- Test 26: plataforma sana si HTTP 200 aunque `dynamic_file_visibility = "not_mounted_in_app"`
- Test 27: plataforma unhealthy si HTTP falla (sin importar visibilidad de archivo)
- Test 28: SSL error en host normalizado → código -2
- Tests 29–30: `_dynamic_file_visibility` — volumen no montado vs archivo ausente

Resultado: **30 passed**.

---

## 2026-05-14 — Fase 4A.2 Fix Crítico Unificado: Tenant Router Health + Dashboard Health Real (BLOQUE 3)

### Objetivo

Cerrar la brecha entre el Router Health Guard (detecta rutas caídas) y el Dashboard (mostraba 100/100 aunque el dominio público fuera inaccesible). Añadir reparación manual de rutas tenant y propagar el estado real a todos los consumers de frontend.

### Restricciones de seguridad

**NO modificado en esta fase**: `platform-frontend.yml`, `platform-api.yml`, ForwardAuth enforcement, Protection Mode, `remediation_engine`, auth/2FA/revoke sessions, npm/pnpm deploy, Docker Compose global, DNS, archivos de clientes, bases de datos de clientes.

### Arquitectura del fix

El canal de información es:
```
router_health_guard_job()
  → system_incidents (source='router_health_guard', open)
    → get_dashboard_summary() overlay
      → healthData en frontend (score=0, public_reachable=False, router_incident_type)
        → DashboardOverview, HostingList, useAIAdvisory (todos leen el mismo healthData)
```

### BLOQUE 3.1 — `app/services/router_health_guard.py`

**`ensure_tenant_traefik_route(hosting_id, dry_run=True) -> dict`** (nueva función):
- Valida: hosting `status='active'`, contenedor corriendo, `subdomain` y `container_name` presentes
- Genera YAML canónico con `hg-forwardauth@docker` middleware, `priority: 50` (menos que plataforma `100`), service `http://{container_name}:80`
- Si `dry_run=False`: backup del archivo existente antes de sobrescribir, escribe en `/opt/traefik-dynamic/{hosting_id}.yml`
- Retorna `{"error": str}` en caso de fallo; dict con `dry_run`, `yaml_content`, `path`, `backed_up` en caso de éxito

**`_resolve_tenant_router_incidents(hosting_id)`** (nueva función):
- Consulta `system_incidents` WHERE `source_table='router_health_guard'`, `status='open'`, `hosting_id` matching
- Llama `_resolve_incident` para cada uno con `extra_evidence={"resolved_reason": "router_health_recovered"}`

**Auto-resolve en `_check_tenant_hosting()`**:
- Si `healthy=True`: llama `_resolve_tenant_router_incidents(hosting_id)` con try/except silencioso
- Los incidentes se resuelven automáticamente cuando la ruta vuelve a funcionar

### BLOQUE 3.2 — `app/api/routes/admin_router_health.py`

**`POST /admin/router-health/tenants/{hosting_id}/repair`**:
```python
class RepairBody(BaseModel):
    dry_run: bool = True

@router.post("/tenants/{hosting_id}/repair")
def repair_tenant(hosting_id: int, body: RepairBody, _: dict = Depends(require_role("admin"))):
    result = ensure_tenant_traefik_route(hosting_id=hosting_id, dry_run=body.dry_run)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
```

### BLOQUE 3.3 — `app/api/routes/alerts.py` — overlay de incidentes de router

**`_get_router_incidents(conn, active_ids) -> dict`** (nueva función interna en `get_dashboard_summary`):
- Query: `SELECT ... FROM system_incidents WHERE source_table='router_health_guard' AND status='open' AND hosting_id=ANY($1)`
- Retorna `{hosting_id: {"incident_type": ..., "severity": ...}}`

**Overlay en `health_map`**:
```python
ri = router_incidents.get(hosting_id)
if ri:
    base = {**base, "score": 0, "status": "critical",
            "public_reachable": False,
            "router_incident_type": ri["incident_type"]}
else:
    base.setdefault("public_reachable", True)
```

Este overlay corre sobre el `base` existente (que ya incluye CPU/RAM/logs del health_engine). Si hay incidente de router activo, el score se fuerza a 0 independientemente de las métricas de container.

### BLOQUE 3.4 — `frontend/src/services/api.js`

```javascript
export const repairRouterHealthTenant = async (hosting_id, dry_run = true) => {
  const response = await api.post(`/admin/router-health/tenants/${hosting_id}/repair`, { dry_run });
  return response.data;
};
```

### BLOQUE 3.5 — `frontend/src/hooks/useAIAdvisory.js` — Tier 0 (Router down)

Añadido antes de Tier 1 (container down) en `evaluateHosting()`:

```javascript
// 0. PUBLIC ROUTE DOWN — Traefik router missing/unreachable.
if (hd.public_reachable === false && hd.router_incident_type) {
    const ROUTER_LABELS = {
        traefik_router_missing_or_unmatched: 'Router Traefik faltante',
        traefik_backend_unreachable:         'Backend inaccesible',
        public_route_timeout:                'Timeout de ruta pública',
        tls_or_certificate_issue:            'Error SSL/TLS',
        container_not_running:               'Contenedor detenido',
    };
    const label = ROUTER_LABELS[hd.router_incident_type] || hd.router_incident_type;
    return {
        severity: 'critical',
        summary: `El dominio público no responde (${label}). El sitio no es accesible.`,
        recommendation: 'Reparar el router Traefik desde el panel de administración → Router Health.',
        requiresAttention: true,
        signals: [label],
    };
}
```

**Por qué Tier 0 toma prioridad**: Si el dominio público no responde, los usuarios no pueden acceder al sitio. Las métricas de container (CPU, RAM) son irrelevantes desde la perspectiva del usuario final. La causa raíz (router caído) debe ganar sobre señales secundarias.

**Guard en Tier 3 (alerts críticas)**: `hd.score < 90 && alerts.some(...)` — previene que una alerta crítica sin resolver de un incidente anterior muestre "CRÍTICO" cuando el score actual es 100 (contradicción "SALUD 100% + CRÍTICO").

### BLOQUE 3.6 — `frontend/src/components/dashboard/DashboardOverview.jsx`

**Nuevas derivaciones**:
```javascript
const brokenRoutes = hostings.filter(
  h => healthData[h.hosting_id]?.public_reachable === false
).length;
const publicOperational = Math.max(0, active - brokenRoutes);
const pct = active > 0 ? Math.round((publicOperational / active) * 100) : 0;
```

**Header status dot**: Color rojo cuando `brokenRoutes > 0`, verde cuando todo operativo.

**"Todo operativo"**: Muestra `"X sitios con ruta caída"` en rojo cuando `brokenRoutes > 0`.

**StatCard "Sitios Activos"**: Value = `publicOperational` (no `active`). Footer muestra "X con ruta caída" en rojo cuando aplica.

**StatCard "Salud General"**: Footer muestra "Rutas públicas caídas" en rojo cuando `brokenRoutes > 0`.

**`SiteRow`**:
- `routerIssue = hd.public_reachable === false`
- Status dot: rojo si `routerIssue`, verde si `status=active`, gris si detenido
- Badge "Ruta caída" en rojo cuando `routerIssue`

### BLOQUE 3.7 — `frontend/src/components/dashboard/HostingList.jsx`

Badge "Web inaccesible" después del badge de salud:
```jsx
{healthData[h.hosting_id]?.public_reachable === false && (
  <div className="text-[10px] px-2 py-0.5 rounded font-bold uppercase tracking-wider bg-red-500/20 text-red-400">
    Web inaccesible
  </div>
)}
```

### BLOQUE 3.8 — `frontend/src/components/admin/RouterHealthPanel.jsx` — TenantRepairButtons

Nuevo componente `TenantRepairButtons` dentro del tab de Tenants:
- Solo visible cuando `r.incident_type === 'traefik_router_missing_or_unmatched'`
- "Simular reparación" → `repairRouterHealthTenant(id, dry_run=true)` — muestra YAML via `<details>`
- "Reparar router" → `window.confirm` con texto exacto: *"Esto solo recrea la ruta Traefik del sitio. No modifica archivos, contenedores, DNS ni datos del cliente."* → `repairRouterHealthTenant(id, dry_run=false)`
- `onRepairDone={load}` — recarga el listado tras reparación exitosa

### BLOQUE 3.9 — Tests añadidos (31–38)

| Test | Función cubierta |
|---|---|
| 31 | `ensure_tenant_traefik_route` dry_run no escribe archivo |
| 32 | YAML generado contiene `hg-forwardauth`, `priority: 50`, service correcto |
| 33 | Rechaza hosting inactivo (status ≠ 'active') |
| 34 | Rechaza si contenedor no corre |
| 35 | En modo live: escribe archivo, hace backup del existente |
| 36 | Overlay de incidente de router fuerza `score=0`, `public_reachable=False` en `get_dashboard_summary` |
| 37 | `_resolve_tenant_router_incidents` resuelve incidentes abiertos del tenant |
| 38 | Auto-resolve: cuando `_check_tenant_hosting` encuentra healthy=True, llama `_resolve_tenant_router_incidents` |

Resultado final: **38 passed**.

### Pendiente de validación en producción

```sql
-- Verificar que el overlay funciona:
SELECT hi.subdomain, si.incident_type, si.status
FROM system_incidents si
JOIN hostings hi ON hi.hosting_id = (si.context_json->>'hosting_id')::int
WHERE si.source_table = 'router_health_guard' AND si.status = 'open';

-- Dashboard debe mostrar score=0 y public_reachable=false para estos hostings.
-- El header debe mostrar "X sitios con ruta caída" en rojo.
-- useAIAdvisory debe emitir advisory critical de Tier 0 para estos hostings.
```

---

## 2026-05-14 — Fase 4A.2 Fix Crítico 2: Circuit Breaker — sync_incidents_feed destruía incidentes de Router Health

### Problema raíz (diagnóstico completo)

Dashboard mostraba 100/100 y "Todo operativo" aunque 4 tenants devolvían 404 público y RouterHealthPanel los marcaba como "Router faltante".

**Causa 1 (crítica): `source_type` incorrecto en emisión de incidentes**

`_emit_tenant_incident()` usaba `source_type="site"`. `sync_site_alerts.py` tiene un loop "resolve by absence":
```python
open_incidents = _query(conn,
    "SELECT correlation_key FROM system_incidents WHERE source_type = 'site' AND status = 'open'")
for inc in open_incidents:
    if inc["correlation_key"] not in seen_keys:  # seen_keys = solo site_alerts
        _resolve_incident(conn, inc["correlation_key"], ...)  # ← borraba router health incidents
```
Las claves de router health (`router_health:traefik_router_missing_or_unmatched:...`) nunca estaban en `seen_keys` (que solo contenía `site_alert:{id}:{level}`). Resultado: cada 120 segundos que corría `sync_incidents_feed`, todos los incidentes de router health de tenants eran resueltos automáticamente.

`_emit_platform_incident()` tenía el mismo bug con `source_type="system"` → `sync_system_alerts.py` los eliminaba igualmente.

**Causa 2 (operacional): logger.info no emitido en `router_health_guard_job()`**

El job solo llamaba `_log_audit_event(...)` (escribe en `orchestrator_events` tabla DB), nunca `logger.info(...)`. Resultado: el job era invisible en `docker compose logs -f scheduler`. No hay evidencia en logs de si el job corre o crashea.

**Causa 3 (operacional): scheduler container no reiniciado tras deploy**

El container `hg_scheduler` estaba corriendo código viejo sin `router_health_guard_job` registrado. Los logs solo mostraban `sync_incidents_feed started/completed`.

### Fix aplicado

**`app/services/router_health_guard.py`**:
- `_emit_platform_incident()`: `source_type="system"` → `source_type="router_health"`
- `_emit_tenant_incident()`: `source_type="site"` → `source_type="router_health"`
- `router_health_guard_job()`: Añadidos `logger.info("router_health_guard_job: starting...")` al inicio y `logger.info("router_health_guard_job: done — platform=X/Y ok, tenants=X/Y ok, unhealthy_tenants=N")` al final. Ahora visible en `docker compose logs -f scheduler`.

**Por qué `source_type="router_health"` es seguro**: Ningún sync handler procesa `source_type='router_health'`. La resolución solo ocurre en `_resolve_tenant_router_incidents()` (cuando la ruta vuelve a responder 200) o manualmente. La query de overlay en `alerts.py` filtra por `source_table='router_health_guard'` (no `source_type`), por lo que sigue funcionando sin cambios.

### Tests añadidos (39–45) — resultado: 45 passed

| Test | Función cubierta |
|---|---|
| 39 | `_emit_tenant_incident` usa `source_type='router_health'` |
| 40 | `_emit_platform_incident` usa `source_type='router_health'` |
| 41 | `sync_site_alerts` NO resuelve incidentes `router_health` (source_type difiere) |
| 42 | `sync_system_alerts` NO resuelve incidentes `router_health` (source_type difiere) |
| 43 | `router_health_guard_job` emite `logger.info` visible en scheduler logs |
| 44 | `scheduler_runner.py` contiene `router_health_guard_job` con `interval=60` |
| 45 | `_emit_tenant_incident` setea `hosting_id` correcto para que `_get_router_incidents()` lo encuentre |

Suite completa: **1022 passed, 1 skipped**.

### Acción requerida en producción

```bash
# Reiniciar el scheduler para cargar el código nuevo:
docker compose up -d --build hg_scheduler

# Verificar en logs (debe aparecer tras ~30s):
docker compose logs -f hg_scheduler | grep router_health_guard_job
# Esperado:
# job router_health_guard_job started (interval=60s)
# router_health_guard_job: starting (REPAIR_MODE=protect)
# router_health_guard_job: done — platform=3/3 ok, tenants=0/4 ok, unhealthy_tenants=4

# Verificar incidentes creados (tras ~60s):
# psql -c "SELECT hosting_id, incident_type, source_type, status FROM system_incidents WHERE source_table='router_health_guard' AND status='open';"
# Esperado: 4 rows con source_type='router_health'

# Verificar que sync_incidents_feed NO los resuelve (esperar 120s más):
# psql -c "SELECT count(*) FROM system_incidents WHERE source_table='router_health_guard' AND status='open';"
# Esperado: sigue siendo 4, no 0

# Dashboard debe mostrar degradado tras el primer ciclo del job.
```

## Cierre — Static Container Mount / Welcome to nginx

Estado: cerrado en producción.

Validación:
- Código nuevo desplegado en app, scheduler y frontend.
- `ensure_static_container_mount`, `check_static_container_mounts`, `static-repair` y detector `Welcome to nginx` presentes dentro del contenedor backend.
- Plataforma: API y frontend HTTP 200.
- Tenants activos: 4/4 HTTP 200.
- `mi-academia` ya no sirve Nginx default; devuelve `<title>Course</title>`.
- `mi-academia` tiene bind mount persistente:
  `/opt/clients/user_1_mi-academia_a3dab0:/usr/share/nginx/html:ro`.
- Router Health reporta:
  `platform=3/3 ok, tenants=4/4 ok, unhealthy_tenants=0, invalid_mounts=0`.
- `/tmp/hg_imports` es escribible por `appuser`.

Pendiente:
- Ejecutar chaos test controlado para validar detección de:
  - `Welcome to nginx`
  - `Mounts=[]`
  - `invalid_container_mount`
  - `static-repair`

  Esta sesión:

Fix tests router_health_guard — 3 tests fallando por firma incorrecta de _classify_failure y aserción de mounts. → 68/68 pass.

Incident Knowledge Base + RAG operacional — 24 runbooks, error_signatures.yml (92 firmas), incident_knowledge_service.py, safe_actions_validator.py, integración en Router Health y Dashboard, endpoints /admin/knowledge/, 32 tests.

Chaos Testing P0 — 8 casos (C01–C08), suite run_chaos_suite.py. 3 fallos detectados y corregidos (firmas faltantes, forbidden_action faltante). → 8/8 PASS, Kali-ready.

Kali Finding: SPA wildcard 200 — Bloque nginx antes del SPA fallback bloqueando 20+ rutas sensibles, runbook FRONTEND_SPA_WILDCARD_200_SENSITIVE_PATHS, 7 firmas nuevas, 55 tests. → 55/55 PASS.

Estado general: 1124 tests pasan. Hay 8 fallos en test_upload_zip_validation.py que existían antes de esta sesión (no los toqué).


Todo funciona. Resumen de lo hecho:

1. Clipboard — isEditableTarget guard

frontend/src/utils/keyboard.js — helpers isEditableTarget() e isClipboardShortcut()
frontend/src/components/FileManager.jsx — guard aplicado al handleKeyDown: si el target es editable y el shortcut es clipboard, retorna sin preventDefault
frontend/src/utils/keyboard.test.js — 20 tests: isEditableTarget para INPUT/TEXTAREA/SELECT/contentEditable, isClipboardShortcut para Ctrl/Cmd+C/V/X/A/Z, y el contrato del handler guardado
2. Dark select — Validador de acción

frontend/src/components/admin/IncidentKnowledgePanel.jsx — reemplazado <select> nativo por custom dark dropdown con estados loading/error/opciones visibles; data-testid en cada opción
Tests actualizados para el nuevo interaction pattern + 3 tests nuevos: carga acciones, error backend visible, loading state
3. Header health contradiction

frontend/src/components/dashboard/StatusCommandBar.jsx — allOk ahora incluye brokenRoutes de healthData[h.hosting_id]?.public_reachable === false; muestra "X sitios con ruta caída" cuando hay 403/526/missing route
frontend/src/components/dashboard/StatusCommandBar.test.jsx — 7 tests: 403 → degraded, 526 → degraded, container running solo no alcanza, tenant inactivo no cuenta
4. Runbooks

docs/incidents/runbooks/TENANT_CLOUDFLARE_526_ORIGIN_TLS_INVALID.md — runbook completo con diferencia 526 vs 525/522/523, diagnóstico, safe/forbidden actions
docs/incidents/runbooks/TENANT_NGINX_403_EMPTY_OR_MISSING_INDEX.md — ya existía de la sesión anterior
Firmas sig_109–117 para 526 y sig_100–108 para 403 en error_signatures.yml
Estado final: 44 tests frontend + 201 tests backend, todos pasan.

All four files updated. Summary of what was done:

error_signatures.yml: Added sig_118–sig_125 — "Read-only file system", "server: nginx", "can't create .../index.html", "origin directo 403" for TENANT_NGINX_403, and "Browser Working", "Host Error", "router_source": "docker_labels", "status_code": 526 for TENANT_CLOUDFLARE_526.

safe_actions.yml: Added 9 new actions: migrate_tenant_route_docker_labels_to_file, validate_origin_tls_direct_resolve, request_letsencrypt_certificate, inspect_traefik_acme_logs, create_placeholder_index_for_empty_static_site, validate_static_index_exists, mark_site_pending_content, write_placeholder_index_to_host_mount, fix_static_file_permissions.

forbidden_actions.yml: Added 6 new entries: disable_tls_verification, turn_off_cloudflare_security_globally, mark_healthy_on_container_running_only, write_to_readonly_container_mount, bypass_forwardauth, delete_client_files.

INCIDENT_INDEX.md: Updated to 26 incidents, added rows 25 and 26, bumped high severity count from 6 to 8, updated coverage note.

74 tests pass (66 existing + 8 new).

Bug 2 fix — _resolve_tenant_router_incidents:

Root cause: r[0] on RealDictCursor rows → KeyError(0) → str(exc) == "0" in the log
Fix: replaced raw cursor with _query() helper (returns list[dict]), access row["correlation_key"]
Changed filter from source_table = 'router_health_guard' to source_type = 'router_health' (more robust, matches what _emit_tenant_incident stores)
Added recovery_evidence with recovered_at, status_code_after, container_running_after, route_source_after
Call site passes actual values from the health check result
Logs count: "resolved 2 incident(s) for hosting_id=56"
Bug 1 fix — E2E script:

Added warn() helper (logs "WARN:" but NOT added as "FAIL:" so doesn't trip OVERALL)
Step 3 changed from fail() to warn() — handles 301, 200-without-Welcome, and timeout gracefully; uses curl -L to follow redirects
emit_report: WARN entries render as [~] **WARN** in markdown, "status":"warn" in JSON — never counted as failures
OVERALL logic: for welcome_to_nginx, adds explicit 4-gate check (incident detected, runbook matched, dashboard degraded, repair successful) in addition to the step-log FAIL scan. The evidence from the live run (301 from Cloudflare + API detection working) would now produce OVERALL=PASSED.

Te lo ordeno desde cero, sin ruido.
Qué estábamos intentando lograr
Vos dijiste algo clave: “si un cliente real se cae, no podemos estar 5 horas sin saber qué pasó”.
Entonces construimos y validamos una capa operativa para que HostingGuard haga esto:
Plain text
Detectar incidente
↓
Clasificarlo
↓
Buscar runbook en el RAG
↓
Mostrar safe actions / forbidden actions
↓
Bajar el score del dashboard
↓
Reparar o guiar reparación
↓
Resolver el incidente cuando vuelve a estar sano
Eso es lo que terminamos validando.
1. Primero arreglamos el problema de rutas y tenants
El problema original fue que los tenants podían estar caídos aunque el dashboard dijera “todo bien”.
Detectamos varios casos reales:
Plain text
404 por router faltante
526 de Cloudflare por certificado/origin inválido
403 de Nginx por sitio vacío/sin index.html
Welcome to nginx aunque el sitio debía tener contenido
contenedor running pero web rota
incidente viejo que quedaba open aunque el sitio ya estaba sano
La conclusión fue:
Plain text
Container running NO significa hosting sano.
HTTP 200 sin mirar body NO significa sano.
Dashboard 100 sin curl público NO sirve.
Por eso se reforzó Router Health.
2. Creamos/fortalecimos el RAG operativo
Antes el RAG era más “documentación”. Ahora lo convertimos en una base de incidentes operativa.
Tiene:
Plain text
docs/incidents/runbooks/
docs/incidents/signatures/error_signatures.yml
docs/incidents/remediation/safe_actions.yml
docs/incidents/remediation/forbidden_actions.yml
docs/incidents/INCIDENT_INDEX.md
El sistema ahora puede recibir un texto como:
Plain text
Welcome to nginx!
y devolver:
Plain text
WELCOME_TO_NGINX_EMPTY_SITE
safe action: recreate_static_nginx_container_with_mount
forbidden actions: delete_client_files, disable_nginx_default_page_check, auto_update_dns
También matchea casos como:
Plain text
Mounts=[]
ROOT_RANDOM 200 text/html 919
client version 1.24 is too old
middleware "hg-forwardauth@docker" does not exist
HTTP/2 526
Read-only file system
403 Forbidden
Esto se validó por backend y por UI.
3. Agregamos la UI “Base de Incidentes”
Ahora en el dashboard admin aparece:
Plain text
Base de Incidentes
Con pestañas:
Plain text
Buscar diagnóstico
Runbooks
Validar acción
Postmortems
Probaste visualmente que el buscador reconoce errores reales. Eso significa que ya no tenés que acordarte todo de memoria: podés pegar un log/error y el sistema te dice qué incidente parece ser.
También arreglamos problemas de UI:
Plain text
Ctrl+C / Ctrl+V en campos editables
Dropdown blanco de “Validar acción”
Header que decía “Todo operativo” aunque había sitios rotos
4. Descubrimos y documentamos dos incidentes nuevos
Mientras probábamos chaos-test, apareció esto:
Incidente A — Cloudflare 526
Síntoma:
Plain text
chaos-test.hostingguard.lat → Cloudflare 526 Invalid SSL certificate
Causa probable:
Plain text
Traefik no tenía route/cert correcto por File Provider.
El tenant dependía de Docker labels.
Cloudflare rechazaba el certificado origin.
Creamos runbook:
Plain text
TENANT_CLOUDFLARE_526_ORIGIN_TLS_INVALID
Después el incidente viejo quedó resuelto con evidencia: status: resolved, status_code_after: 200, resolved_reason: router_health_recovered, matched_runbook_id: TENANT_CLOUDFLARE_526_ORIGIN_TLS_INVALID. �
Pegado text.txt
Incidente B — Nginx 403 por sitio vacío
Después de arreglar la ruta, chaos-test pasó de 526 a 403.
Ahí descubrimos que el sitio estaba vacío. No tenía index.html. Como el mount era read-only dentro del contenedor, no podíamos escribir desde adentro; había que escribir desde el host en:
Plain text
/opt/clients/user_1_chaos-test_d6f6f1/index.html
Creamos runbook:
Plain text
TENANT_NGINX_403_EMPTY_OR_MISSING_INDEX
Y dejaste chaos-test sano: origin directo 200 y Cloudflare público 200.
5. Arreglamos el script Live E2E
El script live_incident_e2e.sh tenía problemas:
Primero no encontraba el tenant porque buscaba en /admin/hostings y la lista podía estar filtrada/paginada. Lo corregimos para usar:
Plain text
GET /admin/hostings/{id}
Después no podía inspeccionar Docker porque deploy no tenía permiso sobre Docker sin sudo. Confirmaste que docker inspect sin sudo daba permission denied, pero con sudo funcionaba. �
Pegado text.txt
Entonces el E2E correcto se corre así:
Bash
sudo env CHAOS_ACCEPT_RISK=true bash scripts/chaos/live_incident_e2e.sh ...
Después había otro falso negativo: Cloudflare devolvía 301/502 y el script lo marcaba como fail, aunque Router Health sí detectaba el incidente. Se corrigió para que eso sea WARN, no FAIL.
6. Corrimos el Live E2E real
Este fue el punto más importante.
Con chaos-test sano, corriste el test:
Plain text
tenant-id: 56
container: user_1_chaos-test_d6f6f1
domain: chaos-test.hostingguard.lat
case: welcome_to_nginx
El test hizo esto:
Plain text
1. Validó que el tenant existe y es descartable.
2. Guardó el estado original del contenedor.
3. Reemplazó temporalmente el contenedor por nginx:alpine.
4. Router Health detectó que el tenant estaba unhealthy.
5. Knowledge/RAG devolvió WELCOME_TO_NGINX_EMPTY_SITE.
6. Dashboard bajó score: mostró 1 tenant unhealthy.
7. Restauró el contenedor original.
8. Router Health confirmó recovery.
9. Resultado final: OVERALL PASSED.
Ese resultado es enorme, porque prueba que HostingGuard ya no solo “tiene RAG”, sino que lo usa durante un incidente real controlado.
7. También arreglamos el auto-resolve de incidentes
Había un bug grave: el incidente viejo 2915 seguía open aunque chaos-test ya estaba sano.
Causa raíz:
Plain text
RealDictCursor devuelve dicts, pero el código accedía como r[0].
Eso generaba KeyError(0), y el log mostraba simplemente ": 0".
Se corrigió para acceder por clave:
Plain text
row["correlation_key"]
Y se cambió el filtro a:
Plain text
source_type = 'router_health'
Después el scheduler resolvió correctamente:
Plain text
router_health_guard: resolved 1 incident(s) for hosting_id=56 (recovered)
Y la DB quedó con:
Plain text
status: resolved
resolved_reason: router_health_recovered
status_code_after: 200
matched_runbook_id: TENANT_CLOUDFLARE_526_ORIGIN_TLS_INVALID
�
Pegado text.txt
Qué significa todo esto en palabras simples
Antes:
Plain text
Se cae un tenant
↓
dashboard puede decir 100%
↓
no sabemos si es Traefik, Cloudflare, Nginx, contenido, mount, Docker Provider
↓
perdemos horas
Ahora:
Plain text
Se cae un tenant
↓
Router Health lo detecta
↓
Dashboard baja score
↓
RAG le asigna runbook
↓
muestra safe actions y forbidden actions
↓
el incidente queda guardado
↓
cuando vuelve a estar sano se marca resolved
Eso es un salto enorme.
Estado final de este bloque
Plain text
P0.2 — Incident Knowledge UI + Live Incident E2E: CERRADO ✅
Quedó validado:
Plain text
Base de Incidentes visible ✅
Buscar diagnóstico funciona ✅
Runbooks funcionan ✅
Safe/forbidden actions existen ✅
Router Health detecta tenants rotos ✅
Dashboard se degrada cuando hay incidente ✅
RAG asocia runbook correcto ✅
Auto-resolve funciona ✅
Live E2E real pasó ✅
Reporte E2E generado ✅

1221 passed, 0 regressions.

Root cause: site_dir was built with an f-string (f"/opt/clients/{container_name}"), bypassing the test fixture's os.path.join patch. os.makedirs was correctly redirected to tmp_path, but os.access(site_dir, os.W_OK) still received the original /opt/clients/… path — which doesn't exist in any test environment — returning False and raising 503 before any zip validation could run.

Fix (2 lines):

hosting.py:1287 — os.path.join("/opt/clients", container_name) so the fixture's join patch redirects site_dir to tmp_path.
test_upload_zip_validation.py:208 — AsyncMock(return_value=(0, "", "")) since run_docker_command_async is now actually awaited in the valid-zip path.

1229 passed (+8 new), 0 regressions.

Summary of all changes:

Root cause: get_hosting(id, user_id) filters WHERE hosting_id = %s AND user_id = %s. Admin tokens carry their own user_id which differs from the hosting owner's → 404.

app/api/routes/hosting.py:

Authorization: replaced get_hosting with get_hosting_any + explicit ownership check. Admin bypasses ownership. Non-owner → 403 (not misleading 404). Deleted hosting → 409.
New _BLOCKED_EXTENSIONS set — .php, .py, .sh, .exe, etc. checked per-file in _safe_extract_zip.
Empty ZIP check → 400 zip_empty.
index.html required at serve root → 400 missing_index_html.
_SWAP_SKIP + atomic swap for host-mount deployments: stage in _new/, backup to _backup/, move into place, roll back on failure → 503 upload_atomic_swap_failed.
Normalized file.filename or "" → no more str | None type errors.
Structured success response: {status, hosting_id, subdomain, url, files_applied, index_html, target_dir}.
tests/test_upload_zip_validation.py:

Fixture: added user_id: 2, status: "active" to mock hosting dict; set both get_hosting.return_value and get_hosting_any.return_value.
8 new regression tests covering the primary 404 bug, admin access, owner access, 403 for non-owner, 404 for missing, 409 for deleted, structured response, and missing_index_html.

Informe — HostingGuard P1 + P2
P1 — Upload ZIP: endpoint devolvía 404/503 para hostings existentes
Problema raíz: get_hosting(id, user_id) filtra WHERE user_id = ?, fallando cuando el admin tiene un user_id distinto al dueño del hosting.

Cambios aplicados en hosting.py:

Autorización reescrita: get_hosting_any(id) + validación de ownership en Python + bypass para admin + bloqueo de deleted
file.filename normalizado a str (era str | None)
site_dir construido con os.path.join(...) en lugar de f-string (necesario para que el fixture de tests pueda parcharlo)
Validaciones añadidas: ZIP vacío, index.html requerido, extensiones bloqueadas
Swap atómico: _new/ → _backup/ → mueve contenido → rollback si falla
Respuesta estructurada: { status, hosting_id, subdomain, url, files_applied, index_html, target_dir }
Tests: 17/17 en test_upload_zip_validation.py ✓

P2 — Provisioning Gate para tenants estáticos
Objetivo: Impedir que un tenant recién creado quede marcado como active si no está operativo.

Archivos nuevos:

Archivo	Descripción
app/services/provisioning_gate.py	12 checks, evaluador por prioridad, ProvisioningGateResult
app/services/traefik_file_provider.py	Crea/borra YAML del File Provider con rename atómico
Jerarquía de estados (mejor → peor):


active → active_with_placeholder → pending_content
       → routing_degraded → routing_failed → provisioning_failed
Cambios en hosting_repository.py:

5 nuevos estados añadidos a VALID_STATUSES.

Integración en create_hosting:

Crea directorio host + placeholder index.html si no existe
Crea Traefik File Provider YAML (tenant-{id}.yml)
Ejecuta gate con check_http=False (TLS/routing no están listos aún)
Actualiza status en DB si no es active
Escribe evento de auditoría hosting.provisioning.gate_passed/gate_failed
Devuelve provisioning_status en la respuesta
Tests: 17/17 en test_provisioning_gate.py ✓

Suite completa: 1246 passed, 1 skipped, 0 failed ✓

Pendiente (no implementado en esta sesión)
Integración de delete_tenant_file_provider al borrar un hosting
Router Health Guard consumiendo ProvisioningGate
Dashboard UI: mostrar estados pending_content, routing_degraded, etc.
Runbook TENANT_ROUTE_DOCKER_LABELS_ONLY en INCIDENT_INDEX.md

---------------------------------------------------------------

## Coolify vs HostingGuard — Benchmark Técnico
Qué es Coolify en realidad
Stack: PHP 78% / Blade 19% / Shell. Laravel + PostgreSQL + Redis + Docker Engine v24+. Traefik v2 por defecto (también Caddy y Nginx). Tiempo real vía Soketi (puerto 6001). Terminal en browser (6002).

Modelo: Control plane que conecta a servidores remotos vía SSH y orquesta Docker en ellos. No corre las apps — las orquesta en tus servidores. Es un PaaS developer self-service, no hosting gestionado.

Conclusión rápida: No son competidores directos. Coolify vende "gestión de N servidores propios". HostingGuard vende "hosting gestionado". El eje de comparación útil es qué patrones técnicos están resueltos allá y no aquí.

Matriz por área
Área	Coolify	HostingGuard	Brecha
Server onboarding	SSH keypair + 4 checks + instala Traefik	Provisioning Gate (12 checks) por tenant	Paradigma distinto — el Gate de HG es equivalente funcional
App deployment	Nixpacks (50+ runtimes), Dockerfile, Compose, PR previews	4 estrategias (Dockerfile, server, static_built, static_pure), webhook HMAC	Sin Nixpacks, sin PR preview environments
Static sites	Toggle + Static buildpack + Traefik	Strategy C + _find_serve_dir + health check post-deploy	Equivalente; HG tiene post-deploy diagnosis que Coolify no
Databases	PostgreSQL, MariaDB, MongoDB, Redis, ClickHouse, SurrealDB, MinIO	Solo MariaDB per-tenant (WordPress)	Gran brecha en variedad y backup automation
Docker orchestration	Standalone + Swarm experimental, cleanup automático por disco	Standalone, container locks, scheduler/worker separados	Falta cleanup automático por presión de disco
Proxy / routing	Traefik + Caddy + Nginx, middleware chains, Cloudflare Tunnel	Traefik + Router Health Guard + custom domain con compound TLD	HG tiene Router Health Guard — Coolify no tiene nada equivalente
TLS / certificados	Let's Encrypt vía Traefik, Cloudflare integration	Let's Encrypt vía Traefik, ssl_status por dominio	Equivalente; HG falta last_cert_renewal + alerta de expiración
Backups	Cron + pg_dump custom format + S3 + IAM policy generation	Solo backup del DB propio (pg_dump en hosting-guard-db)	Gap crítico: datos de tenant (WordPress files + MariaDB) sin backup automatizado
Templates	150+ Compose templates, magic variables (SERVICE_PASSWORD_*)	WordPress+MariaDB y nginx static (opinionated)	HG no compite en marketplace — falta depth en vertical WordPress
Logs / observability	Log drains (Axiom, New Relic), Sentinel CPU/RAM, 6 canales de notificación	Prometheus metrics, log parser, wp attack aggregation, diagnostic engine	HG más sofisticado en WordPress; falta log drain externo y canales Discord/Webhook
Health checks	Docker HEALTHCHECK + Traefik routing a containers saludables	health_engine + post-deploy check + Router Health Guard + diagnostic engine	HG más avanzado para el caso managed; verificar integración Traefik→health
User / team model	Team con owner+members, API tokens con 4 niveles de scope	User con plans, admin/staff, impersonación	Gap crítico para agencias: sin modelo de equipos ni sub-cuentas de cliente
Security model	SSH keypair, Docker network isolation, 2FA, APP_KEY encryption	JWT revocation, CSP/HSTS, path traversal protection, container locks, WP attack detection, audit log inmutable	HG más fuerte en WordPress security; falta 2FA y aislamiento de red por tenant
Installation	curl | bash, single command, 9 pasos automatizados	SaaS — no aplica	N/A por diseño
Monetización	Self-hosted gratis + cloud $5/mes base + $3/mes por servidor	SaaS puro, planes $0–$129/mes, agency focus	Modelos distintos — no compiten
A. Qué estudiar en profundidad
1. Template Magic Variables (SERVICE_PASSWORD_*, SERVICE_FQDN_*)
Generación determinista de secrets por servicio, idempotente entre redeployments. Patrón correcto para inyección de WP_DB_PASSWORD, WP_AUTH_KEY, etc. en tenants de WordPress.

2. Sentinel + CheckAndStartSentinelJob
Contenedor ligero que pushea métricas CPU/RAM + job que monitorea al monitor (auto-restart, auto-update, 120s timeout). Patrón de self-healing monitoring que HG necesita para el health watcher de tenants.

3. Backup pipeline completo
Cron por base de datos + pg_dump --format=custom + S3 con IAM policy generation (JSON mínimo: ListBucket/GetObject/PutObject/DeleteObject a un bucket ARN específico) + retención configurable + trigger manual. Leer especialmente la distinción entre "instance backup" (datos de Coolify) y "application backup" (datos del usuario) — HG debe hacer la misma distinción.

4. Proxy lifecycle en 5 acciones
CheckProxy, GetProxyConfiguration, SaveProxyConfiguration, StartProxy, StopProxy. HG tiene 2 de 5 (write_traefik_config + remove_traefik_config). Falta: CheckProxy (health probe del proxy mismo) y SaveProxyConfiguration (persistencia versionada de config).

5. Team model + API tokens con scope
team_user pivot con roles, API tokens con 4 niveles (read-only, read:sensitive, view:sensitive, *), recursos scoped a teams, env vars compartidas por team. Referencia directa para el modelo de agencias.

B. Qué adaptar (patrón correcto, stack Python/FastAPI/Docker)
1. Backup automático de tenants → S3 (Prioridad: crítica)
ARQ task backup_tenant_mariadb por cron. Por cada tenant activo:


docker exec {container} mariadb-dump --all-databases | gzip → boto3.upload_fileobj → s3://{bucket}/{tenant_id}/{date}/
Stagger con initial_delay = hash(tenant_id) % 3600. Metadata en audit table. Lifecycle policy 30 días. Endpoints: GET /hostings/{id}/backups + POST /hostings/{id}/backups/{backup_id}/restore.

2. Magic env vars para WordPress
Al provisionar: generar WP_ADMIN_PASSWORD, WP_DB_PASSWORD, WP_AUTH_KEY, WP_SECURE_AUTH_KEY, WP_LOGGED_IN_KEY con secrets.token_urlsafe(32), cifrados en reposo. Endpoint GET /hostings/{id}/credentials solo para owner. Elimina la categoría más común de tickets de soporte.

3. Router Health Guard extendido
HG ya tiene admin_router_health.py. Añadir:

GET /admin/router/version → compara versión de Traefik corriendo vs latest stable
traefik_version en tabla de config del servidor
Evento router_version_outdated → pipeline system_incidents con source_type='router'
4. Notificaciones multi-canal
notification_dispatcher.py con registro de canales. Empezar: Email (mailer.py existe) + Discord webhook + webhook genérico. Tabla notification_channels (channel_type, config_json, enabled_events JSON). Eventos a notificar: deploy_failed, container_down, backup_failed, wp_brute_force_detected, ssl_expiry_warning, disk_pressure.

5. Cleanup por presión de disco
ARQ task cada 6 horas. Si df /opt/clients > 85%: prunar containers parados de tenants terminados + imágenes dangling con label managed_by=hostingguard + volumes huérfanos. Skip si algún tenant está en estado starting. Emitir disk_pressure_cleanup_executed como system alert.

6. Rollback de deploy
Formalizar schema de deploy_logs JSONB: deploy_id, strategy, started_at, finished_at, exit_code, commit_sha, phases[]. Implementar POST /hostings/{id}/deployments/{deploy_id}/rollback que re-ejecuta el git_config del deploy anterior con el commit SHA previo.

C. Qué no conviene copiar
Qué	Por qué no
PHP/Laravel	FastAPI + Python es la ventaja competitiva de HG para la capa AI (Anthropic SDK, async I/O). No tocar.
Nixpacks	Sistema de 50+ runtimes. Overkill para el vertical WordPress/agency. Los 4 estrategias de HG cubren el caso de uso.
Docker Swarm	Experimental en Coolify, requiere registry externo + 3 nodos mínimo. Sin beneficio para el modelo single-tenant de HG.
150+ templates	Dilución de foco. HG debe tener 5-10 templates profundos y testeados (WP+MariaDB, WooCommerce+Redis, WP Multisite, staging clone, static). Profundidad sobre amplitud.
Self-hosted gratis	El valor de HG está en las operaciones gestionadas y la capa AI. Regalar la infraestructura canibaliza el producto.
Build servers dedicados	Los builds de HG ya corren en docker run --rm efímeros. Un build server separado añade latencia de red sin beneficio a la escala actual.
D. Dónde HostingGuard puede ganar
1. RAG + Incident Runbooks (vs. docs estáticos de Coolify)
Coolify ante un 502: "revisa la documentación." HG ante un 502: el diagnostic engine corre, el RAG consulta el historial del tenant, y el AI advisory pre-carga la solución en el panel. Si el tenant tuvo PHP memory exhaustion hace 14 días, el runbook lo recuerda y sugiere los cambios exactos (innodb_buffer_pool_size, memory_limit). Esto es un feature de retención de clientes que ningún competidor tiene.

2. Router Health Guard como feature premium
Coolify detecta que un container está unhealthy. No puede detectar que la regla de Traefik de un tenant específico conflictúa con otro, que un cambio de DNS hace 6 horas rompió el routing de un tenant mientras los demás funcionan, o que un dominio custom recién añadido sombrea una regla existente. El mensaje de venta: "Validamos que el routing de tu sitio funciona correctamente antes de que tu cliente lo note."

3. Provisioning Gate como señal de confianza
Coolify valida 4 cosas al añadir un servidor (SSH, Docker version, disco, SSH config). HostingGuard valida 12 cosas antes de que el tenant sea accesible. Usar esto en la página de precios y en el dashboard: indicador de progreso por check, resultado visible. Justifica el precio de Agencia Pro vs. los $5/mes de Coolify cloud.

4. Diagnosis automático como deflector de soporte
El soporte de Coolify es: GitHub issues + Discord + email limitado en cloud. Con diagnostic_engine.py + ai_client.py + ai_diagnosis_repository.py, HG puede responder "¿por qué está lento mi sitio?" antes de que el usuario abra un ticket. Cuando el CPU de un tenant spikea, el pipeline corre automáticamente, identifica la causa (WooCommerce cart SQL, AJAX sin cache, plugin conflict), y empuja un advisory legible al dashboard. Nadie más hace esto.

5. Vertical WordPress/ecommerce (foco que Coolify no tiene)
Coolify despliega desde BitcoinCore hasta Bluesky PDS. No entiende WordPress. HG puede dominar:

WooCommerce Health Score: al provisionar WooCommerce, verificar object cache, HPOS, cart fragments async, compresión de imágenes. Reportar como puntuación.
WordPress Multisite gestionado: POST /hostings/{id}/subsites con DNS automático + routing Traefik. Coolify no tiene conciencia de multisite.
Portal de cliente para agencias: vista read-only por hosting para el cliente final (uptime, último deploy, estado de dominio, historial de backups). Sin acceso al servidor ni a la configuración.
Staging environment clone: POST /hostings/{id}/clone-to-staging crea subdominio de staging con copia de datos de producción. Coolify tiene PR previews para repositorios Git, no clones de datos WordPress.
6. WP Attack Aggregation como diferenciador de seguridad
HG ya tiene aggregate_wp_attacks.py (brute force threshold 5/10min, xmlrpc 3/10min). Coolify no tiene nada equivalente. Packaging: "Detectamos y bloqueamos automáticamente ataques de fuerza bruta y xmlrpc en WordPress." Añadir POST /hostings/{id}/blocked-ips para exponer el bloqueo automático. Widget "Seguridad" en el dashboard con el conteo de ataques del mes.

7. Audit log inmutable como feature de compliance
El audit log de Coolify es mutable (registros de DB estándar). El de HG es append-only por restricción arquitectural. Para agencias con clientes WooCommerce (GDPR, cumplimiento PCI DSS): "Cada acción sobre tu hosting — quién hizo qué, cuándo — queda registrada permanentemente y no puede alterarse." Exponer GET /hostings/{id}/audit-log como endpoint paginado.

Prioridades derivadas del benchmark
Las 5 brechas más importantes que bloquean el pitch de agencias, ordenadas:

#	Feature	Bloquea
1	Backup automático de tenant (MariaDB + files → S3)	Propuesta a cualquier agencia seria
2	Notificaciones multi-canal (Discord + webhook mínimo)	Expectativa baseline de cualquier agencia
3	Modelo de equipos / sub-cuentas (agencia owner + cliente read-only)	Justificación del precio Agencia Pro
4	WooCommerce Health Score	Diferenciador que ningún competidor tiene
5	Staging clone (clone-to-staging)	Workflow de agencias sin esto no arranca

---------------------------------------------------------------

1246 passed, 1 skipped, 0 failures. P2B is complete.

All 8 tasks from the spec are done:

delete_tenant_file_provider called in _do_delete_hosting (non-fatal, covers terminate_hosting_by_user too)
Router Health Guard enriches static tenants via ProvisioningGate (check_http=False) and maps gate status → incident type
Frontend HostingList, StatusCommandBar, and the status classification logic updated for all new statuses
Runbook TENANT_ROUTE_DOCKER_LABELS_ONLY.md created
Signatures sig_128–133 added (plus sig_117/124/127 corrected to the right incident) 6–7. Safe and forbidden actions defined in runbook frontmatter and incident index
scripts/ops/validate_provisioning_gate_live.sh created