# tests/test_rag_tenant_isolation.py
from app.api.tenancy import Tenant
from app.core.rag.documents import KnowledgeDocument
from app.core.rag.tenant_in_memory_provider import TenantInMemoryKnowledgeProvider


def test_rag_isolated_per_tenant():
    docs_by_tenant = {
        "tenant_1": [
            KnowledgeDocument(
                doc_id="t1_doc",
                tags=["ecommerce", "rollback_deploy"],
                content="Tenant 1 rollback strategy.",
                metadata={},
            )
        ],
        "tenant_2": [
            KnowledgeDocument(
                doc_id="t2_doc",
                tags=["ecommerce", "rollback_deploy"],
                content="Tenant 2 DIFFERENT strategy.",
                metadata={},
            )
        ],
    }

    provider = TenantInMemoryKnowledgeProvider(docs_by_tenant)

    decision = {
        "overall_status": "requires_human",
        "project_type": "ecommerce",
        "actions_evaluation": [{"action_type": "rollback_deploy"}],
    }

    tenant_1 = Tenant(tenant_id="tenant_1", name="A")
    tenant_2 = Tenant(tenant_id="tenant_2", name="B")

    ctx1 = provider.fetch_context(tenant_1, decision)
    ctx2 = provider.fetch_context(tenant_2, decision)

    assert len(ctx1) == 1
    assert len(ctx2) == 1
    assert ctx1 != ctx2
    assert "tenant 1" in ctx1[0].lower()
    assert "tenant 2" in ctx2[0].lower()


def test_rag_empty_for_unknown_tenant():
    provider = TenantInMemoryKnowledgeProvider({})
    tenant = Tenant(tenant_id="unknown", name="Unknown")
    decision = {"overall_status": "requires_human"}

    context = provider.fetch_context(tenant, decision)
    assert context == []
