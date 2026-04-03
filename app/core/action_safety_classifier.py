# app/core/action_safety_classifier.py

from app.core.constants import (
    CLASSIFICATION_PROHIBITED,
    CLASSIFICATION_SAFE,
    CLASSIFICATION_SENSITIVE,
)


def classify_action(hosting_type: str, project_type: str, action_type: str, estimated_impact: str) -> dict:
    """
    Clasifica una acción técnica según su nivel de seguridad.
    """

    # Regla 1: Impacto alto siempre es prohibido
    if estimated_impact == "high":
        return {
            "classification": CLASSIFICATION_PROHIBITED,
            "requires_human_approval": True,
            "explanation": "La acción tiene un impacto alto y no puede ejecutarse automáticamente.",
        }

    # Regla 2: Ecommerce + acciones sobre código o datos
    if project_type == "ecommerce" and action_type in {
        "deploy_code",
        "modify_core_code",
        "database_change",
    }:
        return {
            "classification": CLASSIFICATION_SENSITIVE,
            "requires_human_approval": True,
            "explanation": "En un ecommerce, las acciones sobre código o datos requieren aprobación humana.",
        }

    # Regla 3: Hosting compartido no permite acciones avanzadas
    if hosting_type == "shared" and action_type in {
        "edit_configuration",
        "modify_core_code",
        "database_change",
    }:
        return {
            "classification": CLASSIFICATION_PROHIBITED,
            "requires_human_approval": True,
            "explanation": "El hosting compartido no permite este tipo de acciones técnicas.",
        }

    # Regla 4: Acción de bajo impacto y reversible
    if estimated_impact == "low" and action_type == "restart_service":
        return {
            "classification": CLASSIFICATION_SAFE,
            "requires_human_approval": False,
            "explanation": "La acción es de bajo impacto y reversible. Puede ejecutarse automáticamente.",
        }

    # Caso por defecto: prudencia
    return {
        "classification": CLASSIFICATION_SENSITIVE,
        "requires_human_approval": True,
        "explanation": "La acción requiere evaluación humana por seguridad.",
    }
