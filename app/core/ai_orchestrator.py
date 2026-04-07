# app/core/ai_orchestrator.py
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Dict, Optional

LLM_TIMEOUT_SECONDS = 10

from app.api.tenancy import Tenant
from app.core.ai_advisory_engine import generate_advisory
from app.core.ai_cache import get_cached_response, save_to_cache
from app.core.ai_interfaces import AdvisoryLLM, TenantKnowledgeProvider
from app.core.llm.factory import get_llm

logger = logging.getLogger(__name__)


class AIOrchestrator:
    """
    Orquesta Advisory Engine + RAG + LLM + Cache.
    Read-only. Sin side-effects.
    """

    def __init__(
        self,
        knowledge_provider: Optional[TenantKnowledgeProvider] = None,
        llm: Optional[AdvisoryLLM] = None,
    ):
        self.knowledge_provider = knowledge_provider
        self._llm = llm

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm()
        return self._llm

    async def enrich(
        self,
        decision: Dict,
        tenant: Optional[Tenant] = None,
        debug_context: Optional[Dict] = None,
    ) -> Dict:
        try:
            advisory = generate_advisory(decision, debug_context=debug_context)

            # 1. Primero verificar cache (operación barata)
            # Incorporar el hash de debug_context para asegurar que respuestas de bugs diferentes no se crucen
            tenant_id = tenant.tenant_id if tenant else None
            
            cache_decision_key = dict(decision)
            if debug_context:
                # Agregamos una firma ligera de los errores extraídos al hash del decision
                errs = debug_context.get("logs", {}).get("parsed_errors", [])
                cache_decision_key["_debug_hash"] = str([e.get("message") for e in errs])

            cached = get_cached_response(cache_decision_key, tenant_id=tenant_id)
            if cached:
                logger.info("Cache HIT - serving from cache")
                return {
                    **advisory,
                    "llm_explanation": cached,
                    "context_used": [],
                    "from_cache": True,
                }

            # 2. Solo si no hay cache, buscar contexto RAG (operación costosa)
            context = []
            if self.knowledge_provider and tenant:
                context = self.knowledge_provider.fetch_context(
                    tenant=tenant,
                    decision=decision,
                )

            # 3. Llamar al LLM con Timeout
            logger.info(
                "LLM enrich request",
                extra={"tenant_id": tenant_id, "decision_id": decision.get("decision_id"), "has_debug_ctx": bool(debug_context)},
            )
            loop = asyncio.get_running_loop()
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self.llm.generate, decision, context, debug_context)
                try:
                    explanation = await loop.run_in_executor(None, lambda: future.result(timeout=LLM_TIMEOUT_SECONDS))
                except FuturesTimeout:
                    logger.warning(
                        "LLM timeout - devolviendo advisory base",
                        extra={"tenant_id": tenant_id},
                    )
                    return {
                        **advisory,
                        "llm_explanation": None,
                        "context_used": context,
                        "from_cache": False,
                    }

            # 4. Validar output del LLM antes de cachear y devolver
            if not explanation or not isinstance(explanation, str) or not explanation.strip():
                logger.warning(
                    "LLM devolvió output vacío o inválido",
                    extra={"tenant_id": tenant_id},
                )
                return {
                    **advisory,
                    "llm_explanation": None,
                    "context_used": context,
                    "from_cache": False,
                }

            save_to_cache(cache_decision_key, explanation, tenant_id=tenant_id)

            return {
                **advisory,
                "llm_explanation": explanation,
                "context_used": context,
                "from_cache": False,
            }

        except Exception:
            logger.error(
                "Error en enriquecimiento de IA (posible falta de crédito o timeout)",
                exc_info=True,
                extra={"tenant_id": tenant.tenant_id if tenant else None},
            )
            # Fallback al advisory base definido arriba (reglas de negocio)
            return {
                **advisory,
                "llm_explanation": "IA temporalmente fuera de servicio. Reporte basado en reglas internas.",
                "context_used": "N/A",
                "from_cache": False
            }
