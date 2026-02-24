# app/core/diagnostic_engine.py

import uuid

from app.core.constants import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
)


def diagnose(
    hosting_type: str,
    project_type: str,
    symptoms: list[str],
    recent_changes: list[str] | None = None,
) -> dict:
    """
    Analiza síntomas técnicos y devuelve un diagnóstico estructurado.
    """

    diagnosis_id = str(uuid.uuid4())

    # Caso conocido: error de conexión a base de datos
    if "database_connection_error" in symptoms:
        return {
            "diagnosis_id": diagnosis_id,
            "probable_causes": [
                {
                    "cause_code": "db_connection_failed",
                    "technical_explanation": "Database connection refused or unreachable",
                    "human_explanation": "La aplicación no logra conectarse a la base de datos.",
                }
            ],
            "suggested_actions": [
                {
                    "action_type": "restart_service",
                    "priority": 1,
                }
            ],
            "confidence_level": CONFIDENCE_HIGH,
        }

    # Caso conocido: error 500 tras actualización de plugin
    if "error_500" in symptoms and recent_changes and "plugin_update" in recent_changes:
        return {
            "diagnosis_id": diagnosis_id,
            "probable_causes": [
                {
                    "cause_code": "plugin_incompatibility",
                    "technical_explanation": "Internal Server Error likely caused by recent plugin change",
                    "human_explanation": (
                        "El sitio muestra un error interno, probablemente por la reciente actualización de un plugin."
                    ),
                }
            ],
            "suggested_actions": [
                {
                    "action_type": "rollback_plugin",
                    "priority": 1,
                }
            ],
            "confidence_level": CONFIDENCE_HIGH,
        }

    # Caso crítico: Error de checkout en ecommerce tras deploy
    if project_type == "ecommerce" and "checkout_error" in symptoms and recent_changes and "deploy" in recent_changes:
        return {
            "diagnosis_id": diagnosis_id,
            "probable_causes": [
                {
                    "cause_code": "checkout_failure_after_deploy",
                    "technical_explanation": "Checkout functionality failed immediately after a code deployment",
                    "human_explanation": (
                        "Se detectó un fallo en el proceso de compra justo después de los "
                        "últimos cambios. Se recomienda revertir para restaurar las ventas."
                    ),
                }
            ],
            "suggested_actions": [
                {
                    "action_type": "rollback_deploy",
                    "priority": 1,
                }
            ],
            "confidence_level": CONFIDENCE_HIGH,
        }

    # Caso por defecto: diagnóstico desconocido
    return {
        "diagnosis_id": diagnosis_id,
        "probable_causes": [],
        "suggested_actions": [],
        "confidence_level": CONFIDENCE_LOW,
    }
