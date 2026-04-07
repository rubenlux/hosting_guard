# app/core/ai_advisory_engine.py


def generate_advisory(decision_result: dict, debug_context: dict | None = None) -> dict:
    """
    Genera una explicación y advertencias humanas a partir
    de una decisión ya tomada por el DecisionPipeline.

    REGLAS:
    - NO modifica decisiones
    - NO ejecuta acciones
    - NO inventa acciones
    """

    overall_status = decision_result.get("overall_status")
    
    debug_msg = ""
    if debug_context and debug_context.get("logs", {}).get("parsed_errors"):
        err = debug_context["logs"]["parsed_errors"][0]
        debug_msg = f"\nDEBUG DETECTADO: {err['type']} en {err['file']} (Línea {err['line']}). Detalle: {err['message']}."

    # 1️⃣ Caso: acción BLOQUEADA (riesgo alto)
    if overall_status == "blocked":
        return {
            "summary": ("La acción propuesta fue bloqueada por presentar un riesgo alto para el sistema." + debug_msg),
            "risk_notes": ["Ejecutar esta acción podría causar pérdida de datos o interrupciones graves."],
            "recommendation": (
                "No se recomienda ejecutar ninguna acción automática. Un humano debe revisar el caso cuidadosamente."
            ),
            "requires_human_attention": True,
        }

    # 2️⃣ Caso: requiere intervención humana
    if overall_status == "requires_human":
        return {
            "summary": (
                "Se detectó una situación que requiere la revisión y aprobación de un humano antes de continuar." + debug_msg
            ),
            "risk_notes": ["La acción propuesta puede tener impacto en el funcionamiento del sistema."],
            "recommendation": ("Revisar la recomendación técnica y aprobarla manualmente si se considera segura."),
            "requires_human_attention": True,
        }

    # 3️⃣ Caso: estado DESCONOCIDO (incertidumbre)
    if overall_status == "unknown":
        return {
            "summary": ("No se pudo determinar con certeza la causa del problema detectado." + debug_msg),
            "risk_notes": ["La información disponible no es suficiente para una decisión automática."],
            "recommendation": ("Se recomienda que un humano revise el caso para evitar acciones incorrectas."),
            "requires_human_attention": True,
        }

    # 4️⃣ Caso: listo para ejecutar (todo OK)
    if overall_status == "ready_for_execution":
        return {
            "summary": ("Todo se encuentra funcionando correctamente. No se detectaron riesgos."),
            "risk_notes": [],
            "recommendation": "Continuar con el monitoreo normal.",
            "requires_human_attention": False,
        }

    # 5️⃣ Fallback ultra defensivo (no debería ocurrir)
    return {
        "summary": "Estado no reconocido. Se recomienda revisión humana.",
        "risk_notes": [],
        "recommendation": "Escalar el caso a un humano.",
        "requires_human_attention": True,
    }
