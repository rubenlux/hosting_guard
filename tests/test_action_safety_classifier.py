# tests/test_action_safety_classifier.py

from app.core.action_safety_classifier import classify_action


def test_high_impact_action_is_prohibited():
    result = classify_action(
        hosting_type="vps",
        project_type="custom_app",
        action_type="deploy_code",
        estimated_impact="high",
    )

    assert result["classification"] == "PROHIBITED"
    assert result["requires_human_approval"] is True


def test_ecommerce_code_action_requires_human_approval():
    result = classify_action(
        hosting_type="vps",
        project_type="ecommerce",
        action_type="deploy_code",
        estimated_impact="medium",
    )

    assert result["classification"] == "SENSITIVE"
    assert result["requires_human_approval"] is True


def test_shared_hosting_disallows_advanced_actions():
    result = classify_action(
        hosting_type="shared",
        project_type="wordpress",
        action_type="edit_configuration",
        estimated_impact="medium",
    )

    assert result["classification"] == "PROHIBITED"
    assert result["requires_human_approval"] is True


def test_low_impact_reversible_action_is_safe():
    result = classify_action(
        hosting_type="vps",
        project_type="custom_app",
        action_type="restart_service",
        estimated_impact="low",
    )

    assert result["classification"] == "SAFE"
    assert result["requires_human_approval"] is True
