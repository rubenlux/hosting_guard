# app/infra/audit/execution_repository.py
import uuid
from datetime import datetime, timezone
from app.infra.audit.execution_models import ExecutionEvent
from app.infra.db import get_connection
from app.infra.migrations import init_db

class ExecutionRepository:
    """Persistencia PostgreSQL para eventos de ejecución."""
    def __init__(self):
        init_db()

    def save_execution_event(self, tenant_id: str, decision_id: str, action_type: str, status: str) -> ExecutionEvent:
        event = ExecutionEvent(
            execution_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            tenant_id=tenant_id,
            decision_id=decision_id,
            action_type=action_type,
            status=status,
        )

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO execution_events VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                event.execution_id, event.timestamp.isoformat(), event.tenant_id,
                event.decision_id, event.action_type, event.status, event.version,
            ),
        )
        conn.commit()
        return event
