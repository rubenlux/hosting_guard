from app.core.rag.documents import KnowledgeDocument
from app.core.rag.in_memory_provider import InMemoryKnowledgeProvider


def test_rag_returns_relevant_context_for_checkout_rollback():
    docs = [
        KnowledgeDocument(
            doc_id="doc1",
            tags=["ecommerce", "rollback_deploy"],
            content="Incidentes de checkout post-deploy suelen resolverse con rollback inmediato.",
            metadata={"source": "internal", "type": "incident"},
        ),
        KnowledgeDocument(
            doc_id="doc2",
            tags=["wordpress", "plugin_update"],
            content="Errores 500 tras plugins suelen indicar incompatibilidad.",
            metadata={"source": "internal", "type": "incident"},
        ),
    ]

    provider = InMemoryKnowledgeProvider(docs)

    decision = {
        "overall_status": "requires_human",
        "project_type": "ecommerce",
        "actions_evaluation": [{"action_type": "rollback_deploy"}],
    }

    context = provider.fetch_context(decision)

    assert len(context) == 1
    assert "checkout" in context[0].lower()
