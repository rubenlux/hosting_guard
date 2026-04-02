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
    ) -> Dict:
        try:
            advisory = generate_advisory(decision)

            # 1. Primero verificar cache (operación barata)
            cached = get_cached_response(decision)
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
            loop = asyncio.get_running_loop()
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self.llm.generate, decision, context)
                try:
                    explanation = await loop.run_in_executor(None, lambda: future.result(timeout=LLM_TIMEOUT_SECONDS))
                except FuturesTimeout:
                    logger.warning("LLM timeout - devolviendo advisory base")
                    return {
                        **advisory,
                        "llm_explanation": None,
                        "context_used": context,
                        "from_cache": False,
                    }

            save_to_cache(decision, explanation)

            return {
                **advisory,
                "llm_explanation": explanation,
                "context_used": context,
                "from_cache": False,
            }

        except Exception as e:
            logger.error("Error en enriquecimiento de IA", exc_info=True)
            return {"summary": "No disponible", "requires_human_attention": True}
