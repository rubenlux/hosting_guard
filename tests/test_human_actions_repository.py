"""
Tests para HumanActionRepository — sin PostgreSQL real.
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


def test_human_action_builds_correct_model():
    from app.infra.audit.human_repository import HumanActionRepository

    conn, cursor = _mock_conn()
    with patch("app.infra.audit.human_repository.get_connection", return_value=conn), \
         patch("app.infra.audit.human_repository.release_connection"):
        event = HumanActionRepository().save_action(
            tenant_id="tenant_test",
            decision_id="decision_123",
            action_type="approve",
            actor="tester",
            reason="Looks safe",
        )

    assert event.action_type == "approve"
    assert event.reason == "Looks safe"
    assert event.decision_id == "decision_123"
    assert event.tenant_id == "tenant_test"
    assert cursor.execute.called


def test_human_action_reject_type():
    from app.infra.audit.human_repository import HumanActionRepository

    conn, _ = _mock_conn()
    with patch("app.infra.audit.human_repository.get_connection", return_value=conn), \
         patch("app.infra.audit.human_repository.release_connection"):
        event = HumanActionRepository().save_action(
            tenant_id="t2",
            decision_id="d-456",
            action_type="reject",
            actor="admin",
            reason="Too risky",
        )

    assert event.action_type == "reject"
    assert event.actor == "admin"
