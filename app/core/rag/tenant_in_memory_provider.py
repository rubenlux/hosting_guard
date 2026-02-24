# app/core/rag/tenant_in_memory_provider.py
from collections import defaultdict
from typing import Dict, List

from app.api.tenancy import Tenant
from app.core.ai_interfaces import TenantKnowledgeProvider
from app.core.rag.documents import KnowledgeDocument


class TenantInMemoryKnowledgeProvider(TenantKnowledgeProvider):
    """
    RAG in-memory con aislamiento estricto por tenant.
    """

    def __init__(self, documents_by_tenant: Dict[str, List[KnowledgeDocument]]):
        """
        documents_by_tenant:
            tenant_id -> list[KnowledgeDocument]
        """
        self.documents_by_tenant = documents_by_tenant
        self.index_by_tenant = self._build_indexes(documents_by_tenant)

    def _build_indexes(
        self,
        documents_by_tenant: Dict[str, List[KnowledgeDocument]],
    ) -> Dict:
        indexes = {}

        for tenant_id, docs in documents_by_tenant.items():
            index = defaultdict(list)
            for doc in docs:
                for tag in doc.tags:
                    index[tag.lower()].append(doc)
            indexes[tenant_id] = index

        return indexes

    def fetch_context(
        self,
        tenant: Tenant,
        decision: Dict,
    ) -> List[str]:
        index = self.index_by_tenant.get(tenant.tenant_id, {})
        tokens = self._extract_tokens(decision)

        seen = set()
        results: List[str] = []

        for token in tokens:
            for doc in index.get(token, []):
                if doc.doc_id not in seen:
                    seen.add(doc.doc_id)
                    results.append(doc.content)

        return results

    def _extract_tokens(self, decision: Dict) -> List[str]:
        tokens = []

        if "overall_status" in decision:
            tokens.append(decision["overall_status"])

        if "project_type" in decision:
            tokens.append(decision["project_type"])

        for action in decision.get("actions_evaluation", []):
            if "action_type" in action:
                tokens.append(action["action_type"])

        return [t.lower() for t in tokens]
