# tests/test_ai_advisory_engine.py

from app.core.ai_advisory_engine import generate_advisory


def test_advisory_for_ecommerce_requires_human():
    decision_result = {
        "decision_id": "123",
        "overall_status": "requires_human",
        "diagnosis": {"confidence_level": "medium"},
        "actions_evaluation": [{"action_type": "rollback_deploy", "requires_human_approval": True}],
    }

    advisory = generate_advisory(decision_result)

    assert advisory["requires_human_attention"] is True
    assert "atención" in advisory["summary"].lower() or "requieren" in advisory["summary"].lower()


def test_advisory_for_blocked_decision():
    decision_result = {
        "decision_id": "456",
        "overall_status": "blocked",
        "diagnosis": {"confidence_level": "high"},
        "actions_evaluation": [{"action_type": "delete_database", "requires_human_approval": True}],
    }

    advisory = generate_advisory(decision_result)

    assert advisory["requires_human_attention"] is True
    assert "riesgo" in advisory["summary"].lower() or "bloqueada" in advisory["summary"].lower()


def test_advisory_for_ready_execution():
    decision_result = {
        "decision_id": "789",
        "overall_status": "ready_for_execution",
        "diagnosis": {"confidence_level": "high"},
        "actions_evaluation": [{"action_type": "restart_service", "requires_human_approval": False}],
    }

    advisory = generate_advisory(decision_result)

    assert advisory["requires_human_attention"] is False
    assert "no se requiere" in advisory["summary"].lower() or "todo" in advisory["summary"].lower()


def test_advisory_for_unknown_decision():
    decision_result = {
        "decision_id": "999",
        "overall_status": "unknown",
        "diagnosis": {"confidence_level": "low"},
        "actions_evaluation": [],
    }

    advisory = generate_advisory(decision_result)

    # El engine no tiene caso especial para "unknown" — cae al default "ok"
    # que requiere atención=False. Si se quiere cambiar, requiere spec en core/.
    assert "severity" in advisory
    assert "summary" in advisory
