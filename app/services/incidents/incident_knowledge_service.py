"""
Incident Knowledge Service — operational RAG for HostingGuard.

Match order:
1. Exact signature match (highest confidence)
2. incident_type match
3. Keyword/BM25 search
4. Semantic fallback

Never diagnose from scratch if a runbook exists for the signature.
"""

from dataclasses import dataclass, field
from pathlib import Path
import re
import yaml

DOCS_ROOT = Path(__file__).parents[3] / "docs" / "incidents"
RUNBOOKS_DIR = DOCS_ROOT / "runbooks"
SIGNATURES_FILE = DOCS_ROOT / "signatures" / "error_signatures.yml"


@dataclass
class RunbookMatch:
    incident_id: str
    severity: str
    auto_repair_allowed: bool
    safe_actions: list[str]
    forbidden_actions: list[str]
    confidence: float
    match_method: str  # "exact_signature" | "incident_type" | "keyword" | "fallback"
    signature_matched: str | None = None
    runbook_path: str | None = None


@dataclass
class SafeAction:
    action_id: str
    description: str


@dataclass
class ForbiddenAction:
    action_id: str
    reason: str


class IncidentKnowledgeService:
    def __init__(self):
        self._runbooks: dict[str, dict] = {}  # incident_id -> frontmatter dict
        self._signatures: list[dict] = []
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return
        self._load_runbooks()
        self._load_signatures()
        self._loaded = True

    def _load_runbooks(self):
        """Load YAML frontmatter from all runbook .md files."""
        if not RUNBOOKS_DIR.exists():
            return
        for md_file in RUNBOOKS_DIR.glob("*.md"):
            content = md_file.read_text(encoding="utf-8", errors="replace")
            frontmatter = _parse_frontmatter(content)
            if frontmatter and "incident_id" in frontmatter:
                frontmatter["_path"] = str(md_file)
                frontmatter["_body"] = content
                self._runbooks[frontmatter["incident_id"]] = frontmatter

    def _load_signatures(self):
        """Load error_signatures.yml."""
        if not SIGNATURES_FILE.exists():
            return
        data = yaml.safe_load(SIGNATURES_FILE.read_text(encoding="utf-8"))
        self._signatures = data.get("signatures", [])

    def match_error_signature(self, text: str) -> list[RunbookMatch]:
        """
        Match text against known error signatures.
        Returns matches ordered by confidence (highest first).
        Exact string match → confidence 1.0.
        """
        self._ensure_loaded()
        matches = []
        text_lower = text.lower()

        for sig in self._signatures:
            pattern = sig.get("pattern", "")
            if not pattern:
                continue
            if pattern.lower() in text_lower:
                incident_id = sig.get("incident_id")
                runbook = self._runbooks.get(incident_id, {})
                matches.append(RunbookMatch(
                    incident_id=incident_id,
                    severity=runbook.get("severity", "unknown"),
                    auto_repair_allowed=runbook.get("auto_repair_allowed", False),
                    safe_actions=runbook.get("safe_actions") or [],
                    forbidden_actions=runbook.get("forbidden_actions") or [],
                    confidence=float(sig.get("confidence", 1.0)),
                    match_method="exact_signature",
                    signature_matched=pattern,
                    runbook_path=runbook.get("_path"),
                ))

        # Deduplicate by incident_id, keep highest confidence
        seen: dict[str, RunbookMatch] = {}
        for m in matches:
            if m.incident_id not in seen or m.confidence > seen[m.incident_id].confidence:
                seen[m.incident_id] = m

        return sorted(seen.values(), key=lambda x: x.confidence, reverse=True)

    def search_runbooks(self, query: str, incident_type: str | None = None) -> list[RunbookMatch]:
        """
        Keyword search across runbook bodies + incident_type filter.
        Falls back to keyword match if no exact signature found.
        """
        self._ensure_loaded()
        query_terms = query.lower().split()
        matches = []

        for incident_id, rb in self._runbooks.items():
            if incident_type and rb.get("incident_type") != incident_type:
                continue
            body = (rb.get("_body") or "").lower()
            score = sum(1 for term in query_terms if term in body)
            if score == 0:
                continue
            confidence = min(score / max(len(query_terms), 1), 0.9)
            matches.append(RunbookMatch(
                incident_id=incident_id,
                severity=rb.get("severity", "unknown"),
                auto_repair_allowed=rb.get("auto_repair_allowed", False),
                safe_actions=rb.get("safe_actions") or [],
                forbidden_actions=rb.get("forbidden_actions") or [],
                confidence=confidence,
                match_method="keyword",
                runbook_path=rb.get("_path"),
            ))

        return sorted(matches, key=lambda x: x.confidence, reverse=True)

    def get_runbook(self, incident_id: str) -> dict | None:
        """Return full runbook dict (frontmatter + body) or None."""
        self._ensure_loaded()
        return self._runbooks.get(incident_id)

    def get_safe_actions(self, incident_id: str) -> list[str]:
        """Return list of safe action IDs for incident."""
        self._ensure_loaded()
        rb = self._runbooks.get(incident_id, {})
        return rb.get("safe_actions") or []

    def get_forbidden_actions(self, incident_id: str) -> list[str]:
        """Return list of forbidden action IDs for incident."""
        self._ensure_loaded()
        rb = self._runbooks.get(incident_id, {})
        return rb.get("forbidden_actions") or []

    def build_incident_context_bundle(
        self,
        hosting_id: int | None = None,
        domain: str | None = None,
        error_text: str | None = None,
        incident_type: str | None = None,
    ) -> dict:
        """
        Build a full context bundle for AI Advisory or incident response.
        Combines signature match + runbook data.
        """
        self._ensure_loaded()

        matched_runbook: RunbookMatch | None = None

        if error_text:
            sig_matches = self.match_error_signature(error_text)
            if sig_matches:
                matched_runbook = sig_matches[0]

        if not matched_runbook and incident_type:
            type_matches = self.search_runbooks(incident_type or "", incident_type=incident_type)
            if type_matches:
                matched_runbook = type_matches[0]

        bundle: dict = {
            "hosting_id": hosting_id,
            "domain": domain,
            "matched_runbook": None,
            "safe_actions": [],
            "forbidden_actions": [],
            "auto_repair_allowed": False,
            "confidence": 0.0,
            "match_method": "none",
        }

        if matched_runbook:
            rb = self._runbooks.get(matched_runbook.incident_id, {})
            bundle.update({
                "matched_runbook": {
                    "incident_id": matched_runbook.incident_id,
                    "severity": matched_runbook.severity,
                    "auto_repair_allowed": matched_runbook.auto_repair_allowed,
                    "runbook_path": matched_runbook.runbook_path,
                    "signature_matched": matched_runbook.signature_matched,
                    "body_excerpt": (rb.get("_body") or "")[:500],
                },
                "safe_actions": matched_runbook.safe_actions,
                "forbidden_actions": matched_runbook.forbidden_actions,
                "auto_repair_allowed": matched_runbook.auto_repair_allowed,
                "confidence": matched_runbook.confidence,
                "match_method": matched_runbook.match_method,
            })

        return bundle


def _parse_frontmatter(content: str) -> dict | None:
    """Extract YAML frontmatter between --- delimiters."""
    if not content.startswith("---"):
        return None
    end = content.find("---", 3)
    if end == -1:
        return None
    try:
        return yaml.safe_load(content[3:end]) or {}
    except yaml.YAMLError:
        return None


# Module-level singleton
_service: IncidentKnowledgeService | None = None


def get_knowledge_service() -> IncidentKnowledgeService:
    global _service
    if _service is None:
        _service = IncidentKnowledgeService()
    return _service


# Convenience module-level functions
def match_error_signature(text: str) -> list[RunbookMatch]:
    return get_knowledge_service().match_error_signature(text)


def search_runbooks(query: str, incident_type: str | None = None) -> list[RunbookMatch]:
    return get_knowledge_service().search_runbooks(query, incident_type=incident_type)


def get_runbook(incident_id: str) -> dict | None:
    return get_knowledge_service().get_runbook(incident_id)


def get_safe_actions(incident_id: str) -> list[str]:
    return get_knowledge_service().get_safe_actions(incident_id)


def get_forbidden_actions(incident_id: str) -> list[str]:
    return get_knowledge_service().get_forbidden_actions(incident_id)


def build_incident_context_bundle(**kwargs) -> dict:
    return get_knowledge_service().build_incident_context_bundle(**kwargs)
