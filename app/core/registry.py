import logging

logger = logging.getLogger(__name__)

class Registry:
    def __init__(self):
        self._orchestrator = None

    @property
    def orchestrator(self):
        if self._orchestrator is None:
            raise RuntimeError("Orchestrator not initialized")
        return self._orchestrator

    @orchestrator.setter
    def orchestrator(self, val):
        self._orchestrator = val

    def get_orchestrator_safe(self):
        if self._orchestrator is None:
            logger.warning("Inicialización perezosa de Orchestrator vía fallback explícito")
            from app.core.ai_orchestrator import AIOrchestrator
            from app.core.rag.tenant_in_memory_provider import TenantInMemoryKnowledgeProvider
            from app.core.rag.documents import load_tenant_documents
            self._orchestrator = AIOrchestrator(
                knowledge_provider=TenantInMemoryKnowledgeProvider(load_tenant_documents())
            )
        return self._orchestrator

registry = Registry()
