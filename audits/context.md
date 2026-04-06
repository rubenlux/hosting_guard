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


