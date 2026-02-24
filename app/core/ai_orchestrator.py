# app/core/ai_orchestrator.py

import logging
from typing import Dict, Optional

from app.api.tenancy import Tenant
from app.core.ai_advisory_engine import generate_advisory
from app.core.ai_interfaces import AdvisoryLLM, TenantKnowledgeProvider
from app.core.llm.factory import get_llm

logger = logging.getLogger(__name__)


class AIOrchestrator:
    """
    Orquesta Advisory Engine + RAG + LLM.
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
        """
        Devuelve advisory base + (opcional) explicación enriquecida.
        Incluye fallback automático si el LLM falla.
        """

        advisory = generate_advisory(decision)

        # Si no hay RAG o no hay tenant, devolvemos solo el advisory base del core
        if not self.knowledge_provider or not tenant:
            return advisory

        try:
            context = self.knowledge_provider.fetch_context(
                tenant=tenant,
                decision=decision,
            )

            # Llamada al LLM (Real o Fake según configuración)
            explanation = self.llm.generate(decision, context)

            return {
                **advisory,
                "llm_explanation": explanation,
                "context_used": context,
            }
        except Exception as e:
            # Fallback seguro: si el LLM (especialmente el real) falla,
            # devolvemos el advisory base determinista del core.
            logger.error(f"Error en enriquecimiento de IA: {e}")
            return advisory
