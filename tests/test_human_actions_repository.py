from app.infra.audit.human_repository import HumanActionRepository


def test_human_action_is_persisted(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.infra.audit.sqlite.DB_PATH",
        tmp_path / "audit.sqlite",
    )

    repo = HumanActionRepository()

    event = repo.save_action(
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
