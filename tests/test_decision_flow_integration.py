# tests/test_decision_flow_integration.py

from app.core.action_safety_classifier import classify_action
from app.core.diagnostic_engine import diagnose


def test_full_decision_flow_for_plugin_update_error():
    diagnosis = diagnose(
        hosting_type="shared",
        project_type="wordpress",
        symptoms=["error_500"],
        recent_changes=["plugin_update"],
    )

    assert diagnosis["confidence_level"] == "high"
    assert len(diagnosis["suggested_actions"]) > 0

    action = diagnosis["suggested_actions"][0]

    safety_result = classify_action(
        hosting_type="shared",
        project_type="wordpress",
        action_type=action["action_type"],
        estimated_impact="medium",
    )

    assert safety_result["classification"] in {"SENSITIVE", "PROHIBITED"}
    assert safety_result["requires_human_approval"] is True
