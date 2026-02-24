# tests/test_diagnostic_engine.py

from app.core.diagnostic_engine import diagnose


def test_database_connection_error_generates_clear_diagnosis():
    result = diagnose(
        hosting_type="vps",
        project_type="custom_app",
        symptoms=["database_connection_error"],
        recent_changes=[],
    )

    assert result["confidence_level"] == "high"

    assert any(cause["cause_code"] == "db_connection_failed" for cause in result["probable_causes"])

    assert any(action["action_type"] == "restart_service" for action in result["suggested_actions"])


def test_ambiguous_symptoms_return_unknown_diagnosis():
    result = diagnose(
        hosting_type="shared",
        project_type="wordpress",
        symptoms=["random_error_code", "unknown_behavior"],
        recent_changes=[],
    )

    assert result["confidence_level"] == "low"
    assert result["probable_causes"] == []
    assert result["suggested_actions"] == []
    assert result["diagnosis_id"] is not None


def test_error_500_after_plugin_update_suggests_rollback():
    result = diagnose(
        hosting_type="shared",
        project_type="wordpress",
        symptoms=["error_500"],
        recent_changes=["plugin_update"],
    )

    assert result["confidence_level"] == "high"

    assert any(cause["cause_code"] == "plugin_incompatibility" for cause in result["probable_causes"])

    assert any(action["action_type"] == "rollback_plugin" for action in result["suggested_actions"])


def test_ecommerce_checkout_error_after_deploy_is_critical():
    result = diagnose(
        hosting_type="vps",
        project_type="ecommerce",
        symptoms=["checkout_error"],
        recent_changes=["deploy"],
    )

    # No puede ser un diagnóstico desconocido
    assert result["confidence_level"] in {"medium", "high"}

    # Debe identificar una causa relacionada al checkout post-deploy
    assert any(cause["cause_code"] == "checkout_failure_after_deploy" for cause in result["probable_causes"])

    # Debe sugerir una acción de contención/reversión
    assert any(
        action["action_type"] in {"rollback_deploy", "rollback_release"} for action in result["suggested_actions"]
    )
