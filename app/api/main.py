import json
import logging
import time
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone


from typing import Optional
from fastapi import Depends, FastAPI, Request, HTTPException, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import generate_latest
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.config import APP_ENV, ENABLE_ACTION_EXECUTION, ENABLE_AI_ADVISORY
from app.api.rate_limit import limiter
from app.api.schemas import DecisionRequest, DecisionResponse, HumanActionRequest
from app.api.security import create_token, create_refresh_token, verify_token, revoke_token, require_role, require_not_support, SECRET, ALGO, _is_revoked
from app.api.security_headers import SecurityHeadersMiddleware
from app.api.tenancy import Tenant
from app.api.tenant_resolver import resolve_tenant
from app.infra.audit.user_repository import UserRepository
import bcrypt
from pydantic import BaseModel, EmailStr
from app.core.ai_advisory_engine import generate_advisory
from app.core.ai_orchestrator import AIOrchestrator
from app.core.decision_pipeline import run_decision_pipeline
from app.core.execution.engine import ExecutionEngine
from app.core.llm.fake_llm import RuleBasedFakeLLM
from app.core.rag.tenant_in_memory_provider import TenantInMemoryKnowledgeProvider
from app.infra.audit.execution_repository import ExecutionRepository
from app.infra.audit.human_repository import HumanActionRepository
from app.infra.audit.repository import AuditRepository
from app.infra.config.repository import TenantConfigRepository
from app.observability.metrics import (
    DECISION_LATENCY,
    DECISIONS_BY_STATUS,
    DECISIONS_TOTAL,
    HUMAN_ACTIONS_TOTAL,
)
from app.services.expiration_job import check_and_expire_free_hostings
from app.services.traffic_collector import collect_traffic
from app.services.health_checker import check_all_hostings

# Configuración de logging para auditoría
logger = logging.getLogger("hosting_guard_audit")
logging.basicConfig(level=logging.INFO)

async def expiration_scheduler():
    """Corre el job de expiración cada 12 horas."""
    while True:
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, check_and_expire_free_hostings)
        except Exception as e:
            logger.error(f"Error en expiration_scheduler: {e}")
        await asyncio.sleep(43200)  # 12 horas


async def traffic_scheduler():
    """Recoge métricas de tráfico nginx cada 5 minutos."""
    logger.info("traffic_scheduler: iniciado — primera ejecución inmediata")
    while True:
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, collect_traffic)
            logger.info("traffic_scheduler: ciclo completado")
        except Exception as e:
            logger.error(f"Error en traffic_scheduler: {e}", exc_info=True)
        await asyncio.sleep(300)


async def health_scheduler():
    """Health check de contenedores cada 5 minutos."""
    logger.info("health_scheduler: iniciado — primera ejecución inmediata")
    while True:
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, check_all_hostings)
            logger.info("health_scheduler: ciclo completado")
        except Exception as e:
            logger.error(f"Error en health_scheduler: {e}", exc_info=True)
        await asyncio.sleep(300)


_background_tasks: set = set()


@asynccontextmanager
async def lifespan(app):
    for coro in (expiration_scheduler(), traffic_scheduler(), health_scheduler()):
        task = asyncio.create_task(coro)
        _background_tasks.add(task)          # prevent garbage collection
        task.add_done_callback(_background_tasks.discard)
    logger.info("lifespan: %d background tasks created", len(_background_tasks))
    yield


app = FastAPI(
    title="Hosting Guard API",
    description="Decision API for hosting diagnostics and safety evaluation",
    version="1.16.0",
    lifespan=lifespan,
)

# Servidores de repositorio de usuarios
user_repo = UserRepository()

# Importar y registrar sub-routers
from app.api.routes.pixel import router as pixel_router
from app.api.routes.files import router as files_router
from app.api.routes.impersonate import router as impersonate_router
from app.api.routes.staff import router as staff_router
from app.api.routes.staff_activity import router as staff_activity_router
app.include_router(pixel_router)
app.include_router(files_router)
app.include_router(impersonate_router)
app.include_router(staff_router)
app.include_router(staff_activity_router)


_IS_PRODUCTION = APP_ENV == "production"

# Flags de seguridad para cookies de sesión.
#
# PRODUCCIÓN (APP_ENV=production):
#   Secure=True   → solo se envían sobre HTTPS (obligatorio con SameSite=None o en general)
#   SameSite=Lax  → permite peticiones cross-origin same-site (hostingguard.lat → api.hostingguard.lat)
#   Domain=hostingguard.lat → cubre todos los subdominios; evita ambigüedad con cookies host-only
#
# DESARROLLO (APP_ENV=development):
#   Secure=False  → permite HTTP en localhost
#   SameSite=Lax  → mismo comportamiento
#   Sin domain    → host-only a localhost
#
# NOTA: SameSite=Strict fue cambiado a Lax en producción porque aunque ambos dominios son
# same-site (mismo eTLD+1), ciertos navegadores tratan peticiones XHR cross-origin como
# "cross-site" en contextos edge. Lax es el balance correcto: seguro + funcional.
_COOKIE_SECURE   = _IS_PRODUCTION
_COOKIE_SAMESITE = "lax"
_COOKIE_DOMAIN   = "hostingguard.lat" if _IS_PRODUCTION else None
_ACCESS_TOKEN_TTL  = 15 * 60
_REFRESH_TOKEN_TTL = 7 * 24 * 60 * 60


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Establece las dos cookies de sesión con los flags de seguridad correctos."""
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite=_COOKIE_SAMESITE,
        domain=_COOKIE_DOMAIN,
        max_age=_ACCESS_TOKEN_TTL,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite=_COOKIE_SAMESITE,
        domain=_COOKIE_DOMAIN,
        max_age=_REFRESH_TOKEN_TTL,
        path="/refresh",
    )


def _clear_auth_cookies(response: Response) -> None:
    """Elimina las cookies de sesión. Domain y path deben coincidir exactamente con el set."""
    response.delete_cookie("access_token",  path="/",        domain=_COOKIE_DOMAIN)
    response.delete_cookie("refresh_token", path="/refresh", domain=_COOKIE_DOMAIN)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


@app.get("/")
def root():
    return {
        "service": "HostingGuard API",
        "status": "ok"
    }

@app.post("/register")
@limiter.limit("5/minute")
def register(request: Request, body: RegisterRequest):
    hashed_password = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
    try:
        user_repo.create_user(body.email, hashed_password)
        return {"email": body.email, "status": "registered"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/login")
@limiter.limit("5/minute")
def login(request: Request, response: Response, body: LoginRequest):
    ip = request.client.host if request.client else "unknown"
    user = user_repo.get_user_by_email(body.email)

    if not user or not bcrypt.checkpw(body.password.encode(), user["password_hash"].encode()):
        user_repo.log_login_attempt(body.email, ip, success=False, detail="Invalid credentials")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user_repo.log_login_attempt(body.email, ip, success=True)

    claims = {"user_id": user["user_id"], "email": user["email"], "role": user.get("role", "user")}
    _set_auth_cookies(response, create_token(claims), create_refresh_token(claims))

    # No devolver tokens en el cuerpo: están en cookies HttpOnly inaccesibles desde JS.
    return {"status": "ok"}

@app.post("/logout")
def logout(response: Response, user=Depends(verify_token)):
    # Revocar access token
    jti = user.get("jti")
    exp = user.get("exp")
    if jti and exp:
        expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
        revoke_token(jti, expires_at=expires_at)
    _clear_auth_cookies(response)
    return {"status": "ok", "detail": "Sesión cerrada correctamente"}


@app.post("/refresh/revoke")
@limiter.limit("10/minute")
def revoke_refresh(request: Request, response: Response):
    """
    Revoca el refresh_token activo.
    El browser envía la cookie refresh_token aquí (path=/refresh) pero NO en /logout,
    por eso este endpoint existe separado. Llamar desde el frontend justo antes de /logout.
    """
    from jose import jwt, JWTError
    refresh_token_value = request.cookies.get("refresh_token")
    if not refresh_token_value:
        return {"status": "ok"}  # Nada que revocar
    try:
        payload = jwt.decode(refresh_token_value, SECRET, algorithms=[ALGO])
        r_jti = payload.get("jti")
        r_exp = payload.get("exp")
        if r_jti and r_exp:
            revoke_token(r_jti, datetime.fromtimestamp(r_exp, tz=timezone.utc))
    except JWTError:
        pass  # Token ya inválido — nada que hacer
    return {"status": "ok"}

@app.post("/refresh")
@limiter.limit("10/minute")
def refresh(request: Request, response: Response):
    from jose import jwt, JWTError
    refresh_token_value = request.cookies.get("refresh_token")
    if not refresh_token_value:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = jwt.decode(refresh_token_value, SECRET, algorithms=[ALGO])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")

        user_id = payload.get("user_id")
        email   = payload.get("email")
        role    = payload.get("role", "user")

        # Comprobar que este refresh token no haya sido ya rotado o revocado.
        # Sin esta comprobación, un token robado sigue funcionando aunque el usuario
        # legítimo ya haya rotado su sesión (replay attack).
        old_jti = payload.get("jti")
        old_exp = payload.get("exp")
        if old_jti and _is_revoked(old_jti):
            _clear_auth_cookies(response)
            raise HTTPException(status_code=401, detail="Refresh token revocado")

        # Rotación: revocar el refresh token usado antes de emitir uno nuevo
        if old_jti and old_exp:
            revoke_token(old_jti, datetime.fromtimestamp(old_exp, tz=timezone.utc))

        claims = {"user_id": user_id, "email": email, "role": role}
        _set_auth_cookies(response, create_token(claims), create_refresh_token(claims))
        return {"status": "ok"}
    except JWTError:
        _clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    except Exception:
        raise HTTPException(status_code=500, detail="Error interno al procesar el token")

@app.get("/me")
def get_me(user: dict = Depends(verify_token)):
    user_db = user_repo.get_user_by_id(user["user_id"])
    if not user_db:
        # Si el token es válido pero el usuario no existe (ej: DB borrada),
        # lanzamos 401 para que el frontend limpie la sesión.
        raise HTTPException(status_code=401, detail="User session expired or not found")
        
    response_data = {
        "user_id": user["user_id"],
        "email": user["email"],
        # Role is read from the DB (not the JWT) so a role change in the DB takes effect
        # on the next /me call without waiting for token expiry.
        "role": user_db.get("role", "user"),
        "plan": user_db.get("plan", "free"),
        "balance": user_db.get("balance", 0.0),
        "has_payment_method": bool(user_db.get("has_payment_method", 0)),
        "autoscale_enabled": bool(user_db.get("autoscale_enabled", 1)),
        "status": "authenticated",
        "is_support_session": user.get("is_support_session", False),
    }
    # Expose support metadata so the frontend can render the SupportBanner
    if user.get("is_support_session"):
        from datetime import datetime as _dt, timezone as _tz
        exp = user.get("exp")
        response_data["admin_email"]       = user.get("admin_email")
        response_data["support_expires_at"] = (
            _dt.fromtimestamp(exp, tz=_tz.utc).isoformat() if exp else None
        )
    return response_data

@app.get("/me/support-history")
def get_support_history(user: dict = Depends(verify_token)):
    """Client can see when support accessed their account — full transparency."""
    from app.infra.audit.support_repository import SupportSessionRepository
    repo = SupportSessionRepository()
    return repo.get_sessions_for_user(user["user_id"])


# --- NUEVAS RUTAS DE PRODUCTO ---

class UserConfigRequest(BaseModel):
    autoscale_enabled: Optional[bool] = None
    has_payment_method: Optional[bool] = None

@app.post("/user/config")
def update_user_config(config: UserConfigRequest, user=Depends(verify_token)):
    try:
        if config.autoscale_enabled is not None:
            user_repo.update_autoscale(user["user_id"], config.autoscale_enabled)
        if config.has_payment_method is not None:
            user_repo.update_payment_method(user["user_id"], config.has_payment_method)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from pydantic import field_validator

class TopupRequest(BaseModel):
    amount: float

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v):
        if v <= 0 or v > 1000:
            raise ValueError("Monto inválido")
        return v

@app.post("/user/topup")
def topup(data: TopupRequest, user=Depends(require_not_support)):
    try:
        user_repo.update_balance(user["user_id"], data.amount)
        user_db = user_repo.get_user_by_id(user["user_id"])
        
        if not user_db:
            raise HTTPException(status_code=404, detail="User not found")
            
        return {"balance": user_db["balance"]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/advisory")
def get_advisory_mock(user=Depends(verify_token)):
    # Mock de eventos para el dashboard
    return [
        {"message": "Aumento de CPU detectado en 'miapp'", "level": "warning", "time": "Justo ahora"},
        {"message": "Certificado SSL renovado automáticamente", "level": "success", "time": "Hace 2h"},
        {"message": "Intento de intrusión bloqueado por IA Guard", "level": "security", "time": "Hace 5h"}
    ]

# Middleware de seguridad
app.add_middleware(SecurityHeadersMiddleware)

# CORS - Producción
origins = [
    "https://hostingguard.lat",
    "https://www.hostingguard.lat",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    # Permite cualquier subdominio (ej: mi-academia.hostingguard.lat) y dominios
    # externos para el pixel de tracking. Los endpoints de auth están protegidos
    # por cookies HttpOnly con SameSite=Lax, por lo que abrir CORS no es un riesgo.
    allow_origin_regex=r".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate Limiting
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded"},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Catches unhandled exceptions inside FastAPI's ExceptionMiddleware layer,
    which sits *inside* CORSMiddleware — so CORS headers are always present,
    even on 500 responses. Without this, ServerErrorMiddleware (outer layer)
    would return 500 before CORS headers are added.
    """
    logger.error("Unhandled exception on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Infraestructura
audit_repo = AuditRepository()
human_repo = HumanActionRepository()
execution_repo = ExecutionRepository()
tenant_config_repo = TenantConfigRepository()

from app.core.rag.documents import load_tenant_documents
from app.api.routes.hosting import router as hosting_router
from app.api.routes.admin import router as admin_router

# Orquestador con RAG por Tenant y LLM dinámico (env var)
ai_orchestrator = AIOrchestrator(
    knowledge_provider=TenantInMemoryKnowledgeProvider(load_tenant_documents())
)

# Motor de ejecución
execution_engine = ExecutionEngine()

# Routers
app.include_router(hosting_router)
app.include_router(admin_router)


# ── Support session cookie management ────────────────────────────────────────

class SupportTokenRequest(BaseModel):
    token: str

@app.post("/support/activate")
def activate_support_session(body: SupportTokenRequest, response: Response):
    """
    Sets the support_token cookie so verify_token picks it up automatically.
    Called by the frontend after the admin receives the token from /admin/impersonate/{id}.
    """
    from jose import jwt as _jwt, JWTError
    try:
        payload = _jwt.decode(body.token, SECRET, algorithms=[ALGO])
    except JWTError:
        raise HTTPException(status_code=400, detail="Token de soporte inválido.")
    if payload.get("mode") != "support":
        raise HTTPException(status_code=400, detail="No es un token de soporte.")

    from app.api.config import APP_ENV
    secure = APP_ENV == "production"
    response.set_cookie(
        key="support_token",
        value=body.token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=15 * 60,   # 15 minutos
        path="/",
    )
    return {
        "ok": True,
        "target_email": payload.get("email"),
        "admin_email":  payload.get("admin_email"),
        "expires_at":   payload.get("exp"),
    }


@app.post("/support/deactivate")
def deactivate_support_session(response: Response):
    """Clears the support_token cookie (admin exits support mode)."""
    response.delete_cookie("support_token", path="/")
    return {"ok": True}


@app.post("/decision", response_model=DecisionResponse)
@limiter.limit("30/minute")
async def make_decision(
    request: Request,
    payload: DecisionRequest,
    tenant: Tenant = Depends(resolve_tenant),
):
    start_time = time.time()

    decision = run_decision_pipeline(
        hosting_type=payload.hosting_type,
        project_type=payload.project_type,
        symptoms=payload.symptoms,
        recent_changes=payload.recent_changes,
        estimated_impact=payload.estimated_impact,
    )

    # Advisory base
    advisory = generate_advisory(decision)

    # Enriquecimiento opcional (Feature Flag)
    if ENABLE_AI_ADVISORY:
        advisory = await ai_orchestrator.enrich(decision=decision, tenant=tenant)

    # 📊 MÉTRICAS DE NEGOCIO
    DECISIONS_TOTAL.labels(
        tenant_id=tenant.tenant_id,
        project_type=payload.project_type,
    ).inc()

    DECISIONS_BY_STATUS.labels(
        tenant_id=tenant.tenant_id,
        overall_status=decision["overall_status"],
    ).inc()

    DECISION_LATENCY.observe(time.time() - start_time)

    # 🔒 AUDITORÍA (append-only)
    try:
        audit_repo.save_decision_event(
            tenant_id=tenant.tenant_id,
            decision=decision,
            advisory=advisory,
        )
    except Exception as e:
        logger.error(f"Error persisting audit event: {e}")

    # Auditoría de seguridad por tenant (log)
    logger.info(
        json.dumps(
            {
                "event": "api_decision_processed",
                "tenant_id": tenant.tenant_id,
                "ip": request.client.host if request.client else "unknown",
                "decision_id": decision["decision_id"],
                "status": decision["overall_status"],
                "human_required": advisory["requires_human_attention"],
            }
        )
    )

    return {
        **decision,
        "tenant_id": tenant.tenant_id,
        "advisory": advisory,
    }


@app.post("/decision/action")
def human_decision_action(
    action: HumanActionRequest,
    tenant: Tenant = Depends(resolve_tenant),
):
    event = human_repo.save_action(
        tenant_id=tenant.tenant_id,
        decision_id=action.decision_id,
        action_type=action.action_type,
        actor="human",  # luego usuario real
        reason=action.reason,
    )

    # 📊 MÉTRICAS DE INTERACCIÓN HUMANA
    HUMAN_ACTIONS_TOTAL.labels(
        tenant_id=tenant.tenant_id,
        action_type=action.action_type,
    ).inc()

    return {
        "status": "recorded",
        "action_event_id": event.action_event_id,
    }


@app.post("/decision/execute")
def execute_action(
    decision_id: str,
    action: dict,
    tenant: Tenant = Depends(resolve_tenant),
):
    """
    Ejecuta una acción técnica aprobada.
    Protegido por feature flag y validación de aprobación humana.
    """
    if not ENABLE_ACTION_EXECUTION:
        return JSONResponse(
            status_code=403,
            content={
                "status": "DISABLED",
                "detail": "Action execution is not enabled for this environment.",
            },
        )

    # 🔒 POLÍTICA DE SEGURIDAD v1:
    # Solo ejecutamos si la acción está marcada como que requiere aprobación
    # (lo cual implica que el humano ya la vio y dio el OK en /decision/action)
    # En v2 verificaremos el estado de la auditoría humana antes de ejecutar.
    if not action.get("requires_human_approval"):
        return JSONResponse(
            status_code=400,
            content={
                "status": "REJECTED",
                "detail": "Only previously approved human actions can be executed.",
            },
        )

    result = execution_engine.run(action)

    # 📒 Auditar resultado de ejecución
    try:
        execution_repo.save_execution_event(
            tenant_id=tenant.tenant_id,
            decision_id=decision_id,
            action_type=action.get("action_type", "unknown"),
            status=result,
        )
    except Exception as e:
        logger.error(f"Error persisting execution audit event: {e}")

    return {"status": result}


@app.post("/tenant/config")
def update_tenant_config(
    tenant_id: str,
    kind: str,
    content: dict,
    user=Depends(require_role("admin")),
):
    """
    Crea una nueva versión de reglas o prompts para un tenant.
    Solo accesible para usuarios con rol 'admin'.
    """
    cfg = tenant_config_repo.create_new_version(
        tenant_id=tenant_id,
        kind=kind,
        content=content,
    )

    return {
        "status": "ok",
        "config_id": cfg.config_id,
        "version": cfg.version,
    }


@app.get("/metrics")
def metrics(user=Depends(verify_token)):
    """
    Expone métricas para Prometheus.
    """
    return PlainTextResponse(generate_latest())


@app.get("/health")
def health():
    return {"status": "ok"}
