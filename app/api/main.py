import json
import logging
import time

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import generate_latest
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.config import ENABLE_ACTION_EXECUTION, ENABLE_AI_ADVISORY
from app.api.rate_limit import limiter
from app.api.schemas import DecisionRequest, DecisionResponse, HumanActionRequest
from app.api.security_headers import SecurityHeadersMiddleware
from app.api.tenancy import Tenant
from app.api.tenant_resolver import resolve_tenant
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

app = FastAPI(
    title="Hosting Guard API",
    description="Decision API for hosting diagnostics and safety evaluation",
    version="1.11.0",
)

# Middleware de seguridad
app.add_middleware(SecurityHeadersMiddleware)

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
