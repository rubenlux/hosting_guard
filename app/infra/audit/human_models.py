from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class HumanActionEvent:
    action_event_id: str
    timestamp: datetime
    tenant_id: str
    decision_id: str
    action_type: str  # approve | reject
    actor: str
    reason: str | None
    version: int = 1
