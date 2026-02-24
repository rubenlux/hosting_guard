from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ExecutionEvent:
    """
    Evento de auditoría para la ejecución de una acción.
    """

    execution_id: str
    timestamp: datetime
    tenant_id: str
    decision_id: str
    action_type: str
    status: str  # DRY_RUN_FAIL | EXECUTED | ROLLED_BACK | ABORTED
    version: int = 1
