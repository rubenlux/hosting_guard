import uuid
from datetime import datetime, timezone
from app.infra.audit.human_models import HumanActionEvent
from app.infra.db import get_connection, release_connection

class HumanActionRepository:
    """Persistencia PostgreSQL para acciones humanas."""

    def save_action(self, tenant_id: str, decision_id: str, action_type: str, actor: str, reason: str | None = None) -> HumanActionEvent:
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
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO human_action_events VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    event.action_event_id, event.timestamp.isoformat(), event.tenant_id,
                    event.decision_id, event.action_type, event.actor, event.reason, event.version,
                ),
            )
            conn.commit()
            return event
        except Exception:
            conn.rollback()
            raise
        finally:
            release_connection(conn)
