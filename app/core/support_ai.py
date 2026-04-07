"""
Lógica de IA para el chat de soporte al cliente.

Reutiliza el AIOrchestrator existente sin modificarlo.
Construye un "support decision" sintético compatible con generate_advisory()
y obtiene la respuesta enriquecida del LLM.

Claude responde en español, de forma simple, paso a paso,
y pregunta al final si el problema se resolvió.
"""
import asyncio
import logging
from typing import Dict, List, Optional

from app.core.ai_orchestrator import AIOrchestrator

logger = logging.getLogger(__name__)

# Instancia dedicada para soporte — sin knowledge provider,
# no interfiere con la instancia principal de main.py
_support_orchestrator = AIOrchestrator()

# Mapa de status a prioridad del ticket
_PRIORITY_MAP = {
    "Sitio caído": "high",
    "Error en WordPress": "medium",
    "Sitio lento": "medium",
    "Problema de billing": "low",
    "Ayuda técnica": "medium",
    "Otro": "low",
}


def _build_support_decision(
    category: str,
    description: str,
    ai_prompt_hint: str,
    hosting_data: Optional[Dict],
    message_history: List[Dict],
) -> Dict:
    """
    Construye un dict compatible con generate_advisory() y llm.generate().

    overall_status = 'requires_human' hace que generate_advisory() devuelva
    requires_human_attention=True, lo cual es correcto para soporte:
    siempre hay un humano disponible como escalación.
    """
    history_text = ""
    if message_history:
        lines = []
        for msg in message_history[-6:]:  # últimos 6 mensajes para contexto
            role = {"user": "Cliente", "ai": "IA", "staff": "Colaborador"}.get(
                msg.get("sender_type", ""), "Sistema"
            )
            lines.append(f"{role}: {msg.get('content', '')}")
        history_text = "\n".join(lines)

    hosting_text = ""
    if hosting_data:
        hosting_text = (
            f"Hosting: {hosting_data.get('name', 'N/A')} | "
            f"Plan: {hosting_data.get('plan', 'N/A')} | "
            f"Status: {hosting_data.get('status', 'N/A')} | "
            f"Subdominio: {hosting_data.get('subdomain', 'N/A')}"
        )

    # El campo 'symptoms' es lo que llm.generate() usa como contexto principal
    symptoms = (
        f"[SOPORTE AL CLIENTE]\n"
        f"Categoría: {category}\n"
        f"Tipo de problema: {ai_prompt_hint}\n"
        f"Descripción del cliente: {description}\n"
        f"{f'Datos del hosting: {hosting_text}' if hosting_text else ''}\n"
        f"{f'Historial previo:{chr(10)}{history_text}' if history_text else ''}\n\n"
        f"INSTRUCCIONES PARA LA RESPUESTA:\n"
        f"- Responde en español, de forma clara y simple\n"
        f"- Usa pasos numerados si corresponde\n"
        f"- NO ejecutes acciones, solo sugiere pasos\n"
        f"- Al final pregunta: '¿Esto resolvió tu problema?'\n"
        f"- Si el problema requiere acceso al servidor, indícalo claramente\n"
        f"- Sé empático y profesional"
    )

    return {
        "overall_status": "requires_human",
        "decision_id": f"support_{category}",
        "symptoms": symptoms,
        "diagnosis": f"Ticket de soporte: {category}",
        "recommended_actions": [],
        "confidence_level": "medium",
    }


async def generate_support_response(
    category: str,
    description: str,
    ai_prompt_hint: str = "",
    hosting_data: Optional[Dict] = None,
    message_history: Optional[List[Dict]] = None,
) -> str:
    """
    Genera la respuesta de la IA para un ticket de soporte.

    Usa AIOrchestrator.enrich() — mismo mecanismo que el advisory engine.
    Retorna el llm_explanation si está disponible, o el summary del advisory.
    """
    decision = _build_support_decision(
        category=category,
        description=description,
        ai_prompt_hint=ai_prompt_hint,
        hosting_data=hosting_data,
        message_history=message_history or [],
    )

    try:
        result = await _support_orchestrator.enrich(decision=decision, tenant=None)

        # Preferir la respuesta real del LLM
        if result.get("llm_explanation"):
            return result["llm_explanation"]

        # Fallback: usar el summary del advisory
        summary = result.get("summary", "")
        if summary and summary != "No disponible":
            return summary

        # Fallback final: respuesta genérica útil
        return _fallback_response(category)

    except Exception as exc:
        logger.error("Error en generate_support_response: %s", exc, exc_info=True)
        return _fallback_response(category)


def _fallback_response(category: str) -> str:
    """Respuesta genérica cuando el LLM no está disponible."""
    responses = {
        "Sitio caído": (
            "Entiendo que tu sitio no está respondiendo. Aquí algunos pasos iniciales:\n\n"
            "1. Verificá el panel de control — si aparece como 'stopped', intentá reiniciarlo\n"
            "2. Revisá los logs del contenedor buscando errores recientes\n"
            "3. Verificá que el dominio/subdominio apunte correctamente\n\n"
            "Si el sitio sigue caído después de estos pasos, un colaborador lo revisará directamente.\n\n"
            "¿Esto resolvió tu problema?"
        ),
        "Sitio lento": (
            "Para sitios con lentitud, los pasos más comunes son:\n\n"
            "1. Revisá el uso de CPU y memoria en tu dashboard\n"
            "2. Si usás WordPress, deshabilitá plugins uno a uno para identificar el culpable\n"
            "3. Verificá si tenés muchas peticiones simultáneas (pico de tráfico)\n\n"
            "¿Esto resolvió tu problema?"
        ),
        "Error en WordPress": (
            "Para errores en WordPress:\n\n"
            "1. Accedé al Gestor de Archivos y revisá los logs de PHP/Apache\n"
            "2. Intentá desactivar el último plugin instalado\n"
            "3. Si ves pantalla blanca, habilitá el modo debug en wp-config.php\n\n"
            "¿Esto resolvió tu problema?"
        ),
    }
    return responses.get(
        category,
        (
            "Recibí tu consulta y estoy analizando el problema.\n\n"
            "Si necesitás asistencia inmediata, podés solicitar hablar con un colaborador.\n\n"
            "¿Hay algo más que puedas contarme sobre el problema?"
        ),
    )


def get_ticket_priority(category: str) -> str:
    """Retorna la prioridad por defecto para una categoría."""
    return _PRIORITY_MAP.get(category, "medium")
