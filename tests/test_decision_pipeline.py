# tests/test_decision_pipeline.py

from app.core.decision_pipeline import run_decision_pipeline


def test_decision_pipeline_requires_human_for_plugin_rollback():
    result = run_decision_pipeline(
        hosting_type="shared",
        project_type="wordpress",
        symptoms=["error_500"],
        recent_changes=["plugin_update"],
        estimated_impact="medium",
    )

    # El pipeline debe generar un resultado trazable
    assert result["decision_id"] is not None

    # El diagnóstico debe ser confiable
    assert result["diagnosis"]["confidence_level"] == "high"

    # Debe haber al menos una acción evaluada
    assert len(result["actions_evaluation"]) > 0

    action_eval = result["actions_evaluation"][0]

    # La acción propuesta debe existir y haber sido evaluada por seguridad
    assert action_eval["action_type"] == "rollback_plugin"
    assert action_eval["requires_human_approval"] is True

    # El estado global debe reflejar que se necesita un humano
    assert result["overall_status"] == "requires_human"
