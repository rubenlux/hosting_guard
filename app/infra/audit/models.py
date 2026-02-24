from dataclasses import dataclass
from datetime import datetime
from typing import Dict


@dataclass(frozen=True)
class DecisionEvent:
    event_id: str
    timestamp: datetime
    tenant_id: str
    decision_id: str
    overall_status: str
    confidence_level: str
    requires_human_attention: bool
    payload_min: Dict
    version: int = 1
