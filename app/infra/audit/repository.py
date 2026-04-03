# app/infra/audit/repository.py
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict

from app.infra.audit.models import DecisionEvent
from app.infra.audit.sqlite import get_connection, init_db

logger = logging.getLogger(__name__)

_db_initialized = False


class AuditRepository:
    """
    Persistencia append-only de eventos de decisión.
    """

    def __init__(self):
        global _db_initialized
        if not _db_initialized:
            init_db()
            _db_initialized = True

    def save_decision_event(
        self,
        tenant_id: str,
        decision: Dict,
        advisory: Dict,
    ) -> DecisionEvent:
        try:
            diagnosis = decision["diagnosis"]
            event = DecisionEvent(
                event_id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
                tenant_id=tenant_id,
                decision_id=decision["decision_id"],
                overall_status=decision["overall_status"],
                confidence_level=diagnosis["confidence_level"],
                requires_human_attention=advisory["requires_human_attention"],
                payload_min={
                    "actions_count": len(decision.get("actions_evaluation", [])),
                },
            )
        except KeyError as e:
            raise ValueError(f"save_decision_event: missing required field {e}") from e

        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO decision_events (
                    event_id, timestamp, tenant_id, decision_id,
                    overall_status, confidence_level,
                    requires_human_attention, payload_min, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        except Exception:
            logger.exception(
                "Failed to persist decision event for tenant=%s decision=%s",
                tenant_id,
                decision.get("decision_id"),
            )
            raise

        return event
