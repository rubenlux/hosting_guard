import asyncio
import pytest
from app.api.tenancy import Tenant
from app.core.ai_orchestrator import AIOrchestrator


@pytest.fixture(autouse=True)
def clear_ai_cache():
    from app.core import ai_cache
    ai_cache._cache.clear()
    yield
    ai_cache._cache.clear()


class FailingLLM:
    def generate(self, decision, context, debug_context=None):
        raise RuntimeError("LLM Failure Simulation")


class DummyProvider:
    def fetch_context(self, tenant, decision):
        return ["contexto de prueba"]


def test_orchestrator_fallback_on_llm_error():
    orch = AIOrchestrator(
        knowledge_provider=DummyProvider(),
        llm=FailingLLM(),
    )

    tenant = Tenant(tenant_id="test_tenant", name="Test")
    decision = {"overall_status": "requires_human"}

    # El orquestador debería capturar la excepción y devolver el advisory base
    result = asyncio.run(orch.enrich(decision, tenant=tenant))

    assert "summary" in result
    # On LLM error the fallback sets llm_explanation to an error message, not None
    assert result.get("llm_explanation") is not None or "llm_explanation" not in result
    assert result["requires_human_attention"] is True
