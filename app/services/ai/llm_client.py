"""
llm_client — LLM wrapper for AI incident diagnosis.

Builds structured Spanish prompts from incident context, calls Claude,
and returns validated diagnosis dicts. Falls back to rule_based_diagnostics
if the LLM is unavailable or returns invalid JSON.
"""
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

AI_DIAGNOSTIC_PROMPT_VERSION = "ai_diagnostics_v1"

_REQUIRED_FIELDS = frozenset({
    "summary", "root_cause", "recommended_next_steps",
    "customer_message", "confidence",
})


def build_diagnosis_prompt(context: dict) -> str:
    context_json = json.dumps(context, ensure_ascii=False, indent=2, default=str)
    return f"""Sos un ingeniero de infraestructura senior de HostingGuard, una plataforma SaaS de hosting gestionado.

Analizá el siguiente incidente técnico y generá un diagnóstico estructurado en español.

CONTEXTO DEL INCIDENTE:
{context_json}

Respondé EXCLUSIVAMENTE con un JSON válido con la siguiente estructura (sin texto adicional):

{{
  "summary": "Resumen ejecutivo del problema en 1-2 oraciones",
  "root_cause": "Causa raíz técnica detallada",
  "recommended_next_steps": [
    "Paso 1 de acción concreta",
    "Paso 2 de acción concreta"
  ],
  "customer_message": "Mensaje claro para el usuario final, sin jerga técnica",
  "admin_notes": "Notas internas para el equipo de ops",
  "confidence": 0.85
}}

Reglas:
- confidence entre 0.0 y 1.0
- recommended_next_steps: lista de 2 a 5 pasos concretos y accionables
- customer_message: claro, empático, sin culpar al usuario
- No ejecutes ninguna acción. Solo diagnosticá.
- Respondé solo con el JSON, sin markdown ni explicaciones adicionales."""


def _validate_diagnosis(parsed: dict) -> bool:
    if not isinstance(parsed, dict):
        return False
    missing = _REQUIRED_FIELDS - set(parsed.keys())
    if missing:
        return False
    if not isinstance(parsed.get("recommended_next_steps"), list):
        return False
    conf = parsed.get("confidence")
    if not isinstance(conf, (int, float)) or not (0.0 <= conf <= 1.0):
        return False
    return True


def generate_diagnosis(context: dict) -> tuple[dict, str]:
    """
    Call the LLM and return (diagnosis_dict, model_name).
    Falls back to rule_based_diagnostics on any failure.
    """
    from app.services.ai_client import call_llm
    from app.core.llm.safe_parser import safe_parse_llm
    from app.services.ai.rule_based_diagnostics import diagnose_without_llm
    import os

    incident_type = context.get("incident_type", "")
    model = os.getenv("LLM_MODEL", "claude-sonnet-4-6")

    try:
        prompt = build_diagnosis_prompt(context)
        raw = call_llm(prompt)
        parsed = safe_parse_llm(raw)
        if _validate_diagnosis(parsed):
            parsed.setdefault("diagnosis_source", "llm")
            return parsed, model
        logger.warning(
            "generate_diagnosis: LLM response failed validation for %s — using rule_based",
            incident_type,
        )
    except Exception as exc:
        logger.warning("generate_diagnosis: LLM call failed (%s) — using rule_based", exc)

    return diagnose_without_llm(incident_type, context), "rule_based"
