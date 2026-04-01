import json
import logging
import time
import asyncio
from contextlib import asynccontextmanager


from typing import Optional
from fastapi import Depends, FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import generate_latest
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.config import ENABLE_ACTION_EXECUTION, ENABLE_AI_ADVISORY
from app.api.rate_limit import limiter
from app.api.schemas import DecisionRequest, DecisionResponse, HumanActionRequest
from app.api.security import create_token, create_refresh_token, verify_token, SECRET, ALGO
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

# Configuración de logging para auditoría
logger = logging.getLogger("hosting_guard_audit")
logging.basicConfig(level=logging.INFO)

async def expiration_scheduler():
    """Corre el job de expiración cada 12 horas."""
    from app.services.expiration_job import check_and_expire_free_hostings
    while True:
        try:
            check_and_expire_free_hostings()
        except Exception as e:
            logger.error(f"Error en expiration_scheduler: {e}")
        await asyncio.sleep(43200)  # 12 horas


@asynccontextmanager
async def lifespan(app):
    asyncio.create_task(expiration_scheduler())
    yield


app = FastAPI(
    title="Hosting Guard API",
    description="Decision API for hosting diagnostics and safety evaluation",
    version="1.16.0",
    lifespan=lifespan,
)

# Servidores de repositorio de usuarios
user_repo = UserRepository()

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
def register(request: RegisterRequest):
    import hashlib
    safe_pass = hashlib.sha256(request.password.encode()).hexdigest()
    hashed_password = bcrypt.hashpw(safe_pass.encode(), bcrypt.gensalt()).decode()
    try:
        user_id = user_repo.create_user(request.email, hashed_password)
        return {"user_id": user_id, "email": request.email}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/login")
def login(request: LoginRequest):
    user = user_repo.get_user_by_email(request.email)
    import hashlib
    safe_pass = hashlib.sha256(request.password.encode()).hexdigest()
    
    if not user or not bcrypt.checkpw(safe_pass.encode(), user["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    return {
        "access_token": create_token({"user_id": user["user_id"], "email": user["email"]}),
        "refresh_token": create_refresh_token({"user_id": user["user_id"], "email": user["email"]})
    }

@app.post("/refresh")
def refresh(refresh_token: str):
    try:
        from jose import jwt, JWTError
        payload = jwt.decode(refresh_token, SECRET, algorithms=[ALGO])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        
        user_id = payload.get("user_id")
        email = payload.get("email")
        
        return {
            "access_token": create_token({"user_id": user_id, "email": email})
        }
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/me")
def get_me(user: dict = Depends(verify_token)):
    user_db = user_repo.get_user_by_id(user["user_id"])
    if not user_db:
        # Si el token es válido pero el usuario no existe (ej: DB borrada),
        # lanzamos 401 para que el frontend limpie la sesión.
        raise HTTPException(status_code=401, detail="User session expired or not found")
        
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "balance": user_db.get("balance", 0.0),
        "has_payment_method": bool(user_db.get("has_payment_method", 0)),
        "autoscale_enabled": bool(user_db.get("autoscale_enabled", 1)),
        "status": "authenticated"
    }

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

class TopupRequest(BaseModel):
    amount: float

@app.post("/user/topup")
def topup(data: TopupRequest, user=Depends(verify_token)):
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


# Infraestructura
audit_repo = AuditRepository()
human_repo = HumanActionRepository()
execution_repo = ExecutionRepository()
tenant_config_repo = TenantConfigRepository()

from app.core.llm.factory import get_llm
from app.api.routes.hosting import router as hosting_router

# Orquestador con RAG por Tenant y LLM dinámico (env var)
from app.core.llm.factory import get_llm
ai_orchestrator = AIOrchestrator(
    knowledge_provider=TenantInMemoryKnowledgeProvider({}),
    llm=get_llm()
)

# Motor de ejecución
execution_engine = ExecutionEngine()

# Router hosting
app.include_router(hosting_router)


@app.post("/decision", response_model=DecisionResponse)
@limiter.limit("30/minute")
def make_decision(
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
        advisory = ai_orchestrator.enrich(decision=decision, tenant=tenant)

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
):
    """
    Crea una nueva versión de reglas o prompts para un tenant.
    Endpoint administrativo (debe protegerse en pruducción).
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
def metrics():
    """
    Expone métricas para Prometheus.
    """
    return PlainTextResponse(generate_latest())


@app.get("/health")
def health():
    return {"status": "ok"}
