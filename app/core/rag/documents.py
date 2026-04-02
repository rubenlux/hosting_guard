# app/core/rag/documents.py
from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class KnowledgeDocument:
    doc_id: str
    tags: List[str]
    content: str
    metadata: Dict[str, str]

def load_tenant_documents() -> Dict[str, List[KnowledgeDocument]]:
    """Carga los documentos RAG por tenant. Devuelve vacío para el MVP."""
    return {}
