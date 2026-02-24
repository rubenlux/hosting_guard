# tests/test_ai_orchestrator.py
from app.api.tenancy import Tenant
from app.core.ai_orchestrator import AIOrchestrator


class FakeKnowledgeProvider:
    def fetch_context(self, tenant, decision):
        return [f"Contexto para {tenant.name}: Incidente similar resuelto con rollback."]


class FakeLLM:
    def generate(self, decision, context):
        return "Explicación generada a partir del contexto."


def test_ai_orchestrator_without_llm_returns_base_advisory():
    orchestrator = AIOrchestrator()

    decision = {
        "overall_status": "requires_human",
    }

    tenant = Tenant(tenant_id="t1", name="Client 1")

    result = orchestrator.enrich(decision, tenant=tenant)

    assert "summary" in result
    assert "llm_explanation" not in result


def test_ai_orchestrator_with_llm_enriches_advisory():
    orchestrator = AIOrchestrator(
        knowledge_provider=FakeKnowledgeProvider(),
        llm=FakeLLM(),
    )

    decision = {
        "overall_status": "requires_human",
    }

    tenant = Tenant(tenant_id="t1", name="Client 1")

    result = orchestrator.enrich(decision, tenant=tenant)

    assert "llm_explanation" in result
    assert "context_used" in result
    assert "Explicación" in result["llm_explanation"]
    assert "Client 1" in result["context_used"][0]
