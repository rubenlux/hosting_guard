from typing import List, Optional

from pydantic import BaseModel


class DecisionRequest(BaseModel):
    hosting_type: str
    project_type: str
    symptoms: List[str]
    recent_changes: Optional[List[str]] = []
    estimated_impact: str


class AdvisoryResponse(BaseModel):
    summary: str
    risk_notes: List[str]
    recommendation: str
    requires_human_attention: bool
    llm_explanation: Optional[str] = None
    context_used: Optional[List[str]] = None


class DecisionResponse(BaseModel):
    decision_id: str
    diagnosis: dict
    actions_evaluation: list
    overall_status: str
    tenant_id: str
    advisory: Optional[AdvisoryResponse] = None


class HumanActionRequest(BaseModel):
    decision_id: str
    action_type: str  # approve | reject
    reason: str | None = None
