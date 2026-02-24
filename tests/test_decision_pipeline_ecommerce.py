from app.core.decision_pipeline import run_decision_pipeline


def test_ecommerce_deploy_requires_human_and_is_blocked_or_sensitive():
    result = run_decision_pipeline(
        hosting_type="vps",
        project_type="ecommerce",
        symptoms=["checkout_error"],
        recent_changes=["deploy"],
        estimated_impact="high",
    )

    assert result["diagnosis"]["confidence_level"] == "high"

    assert result["overall_status"] == "blocked"

    for action in result["actions_evaluation"]:
        assert action["requires_human_approval"] is True
