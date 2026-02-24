# app/core/rag/in_memory_provider.py
from collections import defaultdict
from typing import Dict, List

from app.core.ai_interfaces import KnowledgeProvider
from app.core.rag.documents import KnowledgeDocument


class InMemoryKnowledgeProvider(KnowledgeProvider):
    """
    RAG simple basado en matching de tokens y tags.
    Determinista y testeable.
    """

    def __init__(self, documents: List[KnowledgeDocument]):
        self.documents = documents
        self.index = self._build_index(documents)

    def _build_index(self, documents: List[KnowledgeDocument]) -> Dict[str, List[KnowledgeDocument]]:
        index = defaultdict(list)
        for doc in documents:
            for tag in doc.tags:
                index[tag.lower()].append(doc)
        return index

    def fetch_context(self, decision: Dict) -> List[str]:
        """
        Recupera fragmentos relevantes en base a:
        - overall_status
        - project_type
        - action_type(s)
        """
        tokens = self._extract_tokens(decision)
        seen = set()
        results: List[str] = []

        for token in tokens:
            for doc in self.index.get(token, []):
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
