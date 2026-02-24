# app/infra/audit/repository.py
import json
import uuid
from datetime import datetime, timezone
from typing import Dict

from app.infra.audit.models import DecisionEvent
from app.infra.audit.sqlite import get_connection, init_db


class AuditRepository:
    """
    Persistencia append-only de eventos de decisión.
    """

    def __init__(self):
        # Aseguramos que la tabla exista al instanciar
        init_db()

    def save_decision_event(
        self,
        tenant_id: str,
        decision: Dict,
        advisory: Dict,
    ) -> DecisionEvent:
        event = DecisionEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            tenant_id=tenant_id,
            decision_id=decision["decision_id"],
            overall_status=decision["overall_status"],
            confidence_level=decision["diagnosis"]["confidence_level"],
            requires_human_attention=advisory["requires_human_attention"],
            payload_min={
                "actions_count": len(decision.get("actions_evaluation", [])),
            },
        )

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO decision_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.timestamp.isoformat(),
                event.tenant_id,
                event.decision_id,
                event.overall_status,
                event.confidence_level,
                int(event.requires_human_attention),
                json.dumps(event.payload_min),
                event.version,
            ),
        )

        conn.commit()
        conn.close()

        return event
