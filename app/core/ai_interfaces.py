# app/core/ai_interfaces.py

from typing import Dict, List, Protocol

from app.api.tenancy import Tenant


class KnowledgeProvider(Protocol):
    """
    Provee contexto técnico curado (RAG).
    Read-only. Sin efectos secundarios.
    """

    def fetch_context(self, decision: Dict) -> List[str]:
        """
        Devuelve fragmentos de conocimiento relevantes
        para una decisión ya tomada.
        """
        ...

class TenantKnowledgeProvider(Protocol):
    """
    Proveedor de conocimiento aislado por tenant.
    """

    def fetch_context(
        self,
        tenant: Tenant,
        decision: Dict,
    ) -> List[str]:
        """
        Devuelve fragmentos de conocimiento relevantes
        para una decisión ya tomada, filtrados por tenant.
        """
        ...

class AdvisoryLLM(Protocol):
    """
    Genera texto explicativo a partir de hechos.
    NO decide. NO ejecuta.
    """

    def generate(
        self,
        decision: Dict,
        context: List[str],
        debug_context: Dict | None = None
    ) -> str:
        """
        Produce una explicación/recomendación textual.
        """
        ...
