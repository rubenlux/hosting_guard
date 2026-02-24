# app/core/llm/fake_llm.py
from typing import Dict, List

from app.core.ai_interfaces import AdvisoryLLM


class RuleBasedFakeLLM(AdvisoryLLM):
    """
    LLM fake basado en reglas y plantillas.
    Emula razonamiento técnico sin efectos secundarios.
    """

    def generate(self, decision: Dict, context: List[str]) -> str:
        parts: List[str] = []

        # 1️⃣ Estado general
        status = decision.get("overall_status", "unknown")

        if status == "blocked":
            parts.append("La acción fue bloqueada porque presenta un riesgo elevado para el sistema.")
        elif status == "requires_human":
            parts.append("Se requiere la intervención de un humano para revisar esta situación.")
        elif status == "unknown":
            parts.append("No se pudo determinar con certeza la causa del problema con la información disponible.")
        elif status == "ready_for_execution":
            parts.append("No se detectaron riesgos significativos en la acción propuesta.")

        # 2️⃣ Contexto RAG (si existe)
        if context:
            parts.append("Contexto relevante identificado:")
            for item in context:
                parts.append(f"- {item}")

        # 3️⃣ Cierre prudente
        parts.append("Se recomienda actuar con cautela y priorizar la estabilidad del sistema.")

        return "\n".join(parts)
