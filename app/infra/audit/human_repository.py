# app/infra/audit/human_repository.py
import uuid
from datetime import datetime, timezone

from app.infra.audit.human_models import HumanActionEvent
from app.infra.audit.sqlite import get_connection, init_db


class HumanActionRepository:
    """
    Persistencia append-only de acciones humanas.
    """

    def __init__(self):
        init_db()

    def save_action(
        self,
        tenant_id: str,
        decision_id: str,
        action_type: str,
        actor: str,
        reason: str | None = None,
    ) -> HumanActionEvent:
        event = HumanActionEvent(
            action_event_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            tenant_id=tenant_id,
            decision_id=decision_id,
            action_type=action_type,
            actor=actor,
            reason=reason,
        )

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO human_action_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.action_event_id,
                event.timestamp.isoformat(),
                event.tenant_id,
                event.decision_id,
                event.action_type,
                event.actor,
                event.reason,
                event.version,
            ),
        )

        conn.commit()
        conn.close()

        return event
