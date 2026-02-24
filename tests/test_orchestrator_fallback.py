from app.api.tenancy import Tenant
from app.core.ai_orchestrator import AIOrchestrator


class FailingLLM:
    def generate(self, decision, context):
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
    result = orch.enrich(decision, tenant=tenant)

    assert "summary" in result
    assert "llm_explanation" not in result
    assert result["requires_human_attention"] is True
