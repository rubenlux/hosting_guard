"""
Tests para AuditRepository — verifica la lógica Python sin DB real.
get_connection() está mockeado: no se necesita PostgreSQL.
"""
from unittest.mock import MagicMock, patch


def _mock_conn():
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    cursor.fetchall.return_value = []
    cursor.rowcount = 1
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


def test_audit_event_builds_correct_model():
    from app.infra.audit.repository import AuditRepository

    conn, cursor = _mock_conn()
    with patch("app.infra.audit.repository.get_connection", return_value=conn), \
         patch("app.infra.audit.repository.release_connection"):
        decision = {
            "decision_id": "d1",
            "overall_status": "requires_human",
            "diagnosis": {"confidence_level": "medium"},
            "actions_evaluation": [],
        }
        event = AuditRepository().save_decision_event(
            tenant_id="tenant_test",
            decision=decision,
            advisory={"requires_human_attention": True},
        )

    assert event.tenant_id == "tenant_test"
    assert event.decision_id == "d1"
    assert event.requires_human_attention is True
    assert cursor.execute.called


def test_audit_event_actions_count_in_payload():
    from app.infra.audit.repository import AuditRepository

    conn, _ = _mock_conn()
    with patch("app.infra.audit.repository.get_connection", return_value=conn), \
         patch("app.infra.audit.repository.release_connection"):
        decision = {
            "decision_id": "d2",
            "overall_status": "ok",
            "diagnosis": {"confidence_level": "low"},
            "actions_evaluation": [1, 2, 3],
        }
        event = AuditRepository().save_decision_event(
            "t2", decision, {"requires_human_attention": False}
        )
    assert event.payload_min["actions_count"] == 3


def test_audit_event_missing_field_raises():
    from app.infra.audit.repository import AuditRepository

    conn, _ = _mock_conn()
    with patch("app.infra.audit.repository.get_connection", return_value=conn), \
         patch("app.infra.audit.repository.release_connection"):
        try:
            AuditRepository().save_decision_event("t", {"decision_id": "x"}, {})
            assert False, "Debe lanzar error por campo faltante"
        except (ValueError, KeyError):
            pass
