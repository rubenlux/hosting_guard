# app/core/ai_orchestrator.py
import logging
from typing import Dict, Optional

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
        self.llm = llm or get_llm()

    def enrich(
        self,
        decision: Dict,
        tenant: Optional[Tenant] = None,
    ) -> Dict:
        advisory = generate_advisory(decision)

        try:
            context = []
            if self.knowledge_provider and tenant:
                context = self.knowledge_provider.fetch_context(
                    tenant=tenant,
                    decision=decision,
                )

            cached = get_cached_response(decision)
            if cached:
                logger.info("Cache HIT - serving from cache")
                return {
                    **advisory,
                    "llm_explanation": cached,
                    "context_used": context,
                    "from_cache": True,
                }

            explanation = self.llm.generate(decision, context)
            save_to_cache(decision, explanation)

            return {
                **advisory,
                "llm_explanation": explanation,
                "context_used": context,
                "from_cache": False,
            }

        except Exception as e:
            logger.error(f"Error en enriquecimiento de IA: {e}")
            return advisory

        except Exception as e:
            logger.error(f"Error en enriquecimiento de IA: {e}")
            return advisory
