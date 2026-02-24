from app.infra.audit.repository import AuditRepository


def test_audit_event_is_persisted(tmp_path, monkeypatch):
    # Usar DB temporal
    monkeypatch.setattr(
        "app.infra.audit.sqlite.DB_PATH",
        tmp_path / "test_audit.sqlite",
    )

    repo = AuditRepository()

    decision = {
        "decision_id": "d1",
        "overall_status": "requires_human",
        "diagnosis": {"confidence_level": "medium"},
        "actions_evaluation": [],
    }

    advisory = {"requires_human_attention": True}

    event = repo.save_decision_event(
        tenant_id="tenant_test",
        decision=decision,
        advisory=advisory,
    )

    assert event.tenant_id == "tenant_test"
    assert event.requires_human_attention is True
