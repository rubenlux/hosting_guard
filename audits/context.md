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
