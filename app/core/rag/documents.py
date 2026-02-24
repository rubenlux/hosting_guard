# app/core/rag/documents.py
from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class KnowledgeDocument:
    doc_id: str
    tags: List[str]
    content: str
    metadata: Dict[str, str]
