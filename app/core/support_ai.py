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

import hashlib
from datetime import datetime, timezone
from app.core.ai_orchestrator import AIOrchestrator
from app.infra.audit.support_cache_repository import SupportCacheRepository

_support_cache_repo = SupportCacheRepository()

# Configuración de TTL por categoría (en minutos)
_TTL_CONFIG = {
    "Sitio caído": 15,    # 15 min (cambia rápido)
    "Sitio lento": 60,    # 1 hora
    "Error en WordPress": 360, # 6 horas
    "Problema de billing": 5,   # 5 min (muy sensible)
    "Ayuda técnica": 120, # 2 horas
}

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
def _get_sub_intent(description: str) -> str:
    """
    Detecta la sub-intención del mensaje usando una huella digital simple del texto.
    Normaliza el texto para que variaciones mínimas no rompan el cache.
    """
    normalized = description.lower()
    for char in [".", ",", "!", "?", "(", ")", "\n", "\r", "-", "_"]:
        normalized = normalized.replace(char, " ")
    
    # Tomar palabras significativas > 3 letras, ordenarlas para ignorar orden
    words = [w.strip() for w in normalized.split() if len(w.strip()) > 3]
    if not words:
        # Fallback si el mensaje es muy corto
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]
        
    fingerprint = "|".join(sorted(list(set(words))))
    return hashlib.sha256(fingerprint.encode()).hexdigest()[:16]


def _is_cache_valid_for_hosting(cache_entry: Dict, current_hosting: Optional[Dict]) -> bool:
    """
    Verifica si una entrada de cache específica de un hosting sigue siendo válida
    basándose en el estado actual del hosting.
    """
    if not current_hosting or not cache_entry.get("hosting_id"):
        return True # Si es cache general, es válido
        
    # Si el estado del hosting cambió desde que se cacheó, invalidar
    if cache_entry.get("hosting_status_when_cached") != current_hosting.get("status"):
        return False
        
    return True



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
) -> tuple[str, Optional[int]]:
    """
    Genera la respuesta de la IA para un ticket de soporte.
    Retorna (mensaje, cache_id).
    """
    # 1. Detectar intención y buscar en cache inteligente
    sub_intent = _get_sub_intent(description)
    hosting_id = hosting_data.get("hosting_id") if hosting_data else None
    
    cached = _support_cache_repo.get_best_match(category, sub_intent, hosting_id)
    if cached and _is_cache_valid_for_hosting(cached, hosting_data):
        logger.info("Smart Cache HIT for category=%s, intent=%s (score=%s)", 
                    category, sub_intent, cached.get("score"))
        _support_cache_repo.increment_use(cached["cache_id"])
        return cached["ai_response"], cached["cache_id"]

    # 2. Si no hay cache, construir decisión y llamar a IA
    decision = _build_support_decision(
        category=category,
        description=description,
        ai_prompt_hint=ai_prompt_hint,
        hosting_data=hosting_data,
        message_history=message_history or [],
    )

    cache_id = None
    try:
        result = await _support_orchestrator.enrich(decision=decision, tenant=None)
        ai_final_msg = ""

        # Preferir la respuesta real del LLM
        if result.get("llm_explanation"):
            ai_final_msg = result["llm_explanation"]
        else:
            # Fallback: usar el summary del advisory
            summary = result.get("summary", "")
            if summary and summary != "No disponible":
                ai_final_msg = summary
            else:
                ai_final_msg = _fallback_response(category)

        # 3. Guardar en cache inteligente si la respuesta es válida
        if ai_final_msg and ai_final_msg != _fallback_response(category):
            ttl = _TTL_CONFIG.get(category, 60)
            cache_id = _support_cache_repo.save_cache(
                category=category,
                sub_intent=sub_intent,
                problem_summary=description[:200],
                ai_response=ai_final_msg,
                ttl_minutes=ttl,
                hosting_id=hosting_id,
                hosting_status=hosting_data.get("status") if hosting_data else None,
                hosting_updated_at=hosting_data.get("updated_at") if hosting_data else None
            )

        return ai_final_msg, cache_id

    except Exception as exc:
        logger.error("Error en generate_support_response: %s", exc, exc_info=True)
        return _fallback_response(category), None


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
