# app/core/decision_pipeline.py

import logging
import uuid

from app.core.action_safety_classifier import classify_action
from app.core.constants import (
    CLASSIFICATION_PROHIBITED,
    CLASSIFICATION_SAFE,
    CLASSIFICATION_SENSITIVE,
    CONFIDENCE_LOW,
    STATUS_BLOCKED,
    STATUS_READY,
    STATUS_REQUIRES_HUMAN,
    STATUS_UNKNOWN,
)
from app.core.diagnostic_engine import diagnose

logger = logging.getLogger(__name__)

VALID_IMPACTS = {"low", "medium", "high"}


def run_decision_pipeline(
    hosting_type: str,
    project_type: str,
    symptoms: list[str],
    recent_changes: list[str] | None,
    estimated_impact: str,
) -> dict:
    """
    Orquesta el flujo completo de decisión:
    diagnóstico -> evaluación de seguridad de acciones.
    """

    decision_id = str(uuid.uuid4())

    # Validación de inputs en la frontera del sistema
    if not symptoms:
        logger.warning("run_decision_pipeline llamado sin síntomas", extra={"decision_id": decision_id})
    if estimated_impact not in VALID_IMPACTS:
        logger.warning(
            "estimated_impact inválido: '%s'. Tratando como 'high' por seguridad.",
            estimated_impact,
            extra={"decision_id": decision_id},
        )
        estimated_impact = "high"

    # Paso 1: diagnóstico
    diagnosis = diagnose(
        hosting_type=hosting_type,
        project_type=project_type,
        symptoms=symptoms,
        recent_changes=recent_changes or [],
    )

    actions_evaluation = []

    # Paso 2: evaluar seguridad de cada acción sugerida
    for action in diagnosis.get("suggested_actions", []):
        safety = classify_action(
            hosting_type=hosting_type,
            project_type=project_type,
            action_type=action["action_type"],
            estimated_impact=estimated_impact,
        )

        actions_evaluation.append(
            {
                "action_type": action["action_type"],
                "priority": action.get("priority"),
                "safety_classification": safety["classification"],
                "requires_human_approval": safety["requires_human_approval"],
                "explanation": safety.get("explanation"),
            }
        )

    # Paso 3: estado global (reglas mínimas, en orden de prioridad descendente)
    if diagnosis["confidence_level"] == CONFIDENCE_LOW:
        # Sin diagnóstico fiable, escalar siempre a humano
        overall_status = STATUS_UNKNOWN
    elif any(a["safety_classification"] == CLASSIFICATION_PROHIBITED for a in actions_evaluation):
        overall_status = STATUS_BLOCKED
    elif any(a["safety_classification"] == CLASSIFICATION_SENSITIVE for a in actions_evaluation):
        overall_status = STATUS_REQUIRES_HUMAN
    elif all(
        a["safety_classification"] == CLASSIFICATION_SAFE and not a["requires_human_approval"]
        for a in actions_evaluation
    ) and actions_evaluation:
        overall_status = STATUS_READY
    else:
        # Cualquier acción sin clasificación explícitamente segura requiere revisión
        overall_status = STATUS_REQUIRES_HUMAN

    return {
        "decision_id": decision_id,
        "hosting_type": hosting_type,
        "project_type": project_type,
        "diagnosis": {
            "diagnosis_id": diagnosis["diagnosis_id"],
            "probable_causes": diagnosis["probable_causes"],
            "confidence_level": diagnosis["confidence_level"],
        },
        "actions_evaluation": actions_evaluation,
        "overall_status": overall_status,
    }
