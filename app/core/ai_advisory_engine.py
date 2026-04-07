# app/core/ai_advisory_engine.py

def generate_advisory(decision_result: dict, debug_context: dict | None = None) -> dict:
    """
    Genera una explicación y advertencias humanas a partir
    de una decisión ya tomada por el DecisionPipeline.
    """

    overall_status = decision_result.get("overall_status")
    
    # Lógica de detección de señales (Parser)
    parsed_errors = debug_context.get("logs", {}).get("parsed_errors", []) if debug_context else []
    critical_errors = [e for e in parsed_errors if e.get("severity") == "critical"]
    warning_signals = [e for e in parsed_errors if e.get("severity") == "warning"]

    debug_msg = ""
    if critical_errors:
        err = critical_errors[0]
        debug_msg = f"\n🚨 ERROR CRÍTICO: {err['message']} en {err['file']} (Línea {err['line']})."
    elif warning_signals:
        sig = warning_signals[0]
        debug_msg = f"\n⚠️ ADVERTENCIA: Se detectaron señales no críticas (ej: {sig['message']}). Esto puede afectar la experiencia del usuario."

    # 1️⃣ Caso: acción BLOQUEADA (riesgo alto)
    if overall_status == "blocked":
        return {
            "summary": ("La acción propuesta fue bloqueada por presentar un riesgo alto." + debug_msg),
            "risk_notes": ["Riesgo de inestabilidad detectado."],
            "recommendation": "Revisión humana obligatoria.",
            "requires_human_attention": True,
            "severity": "critical"
        }

    # 2️⃣ Caso: requiere intervención humana (o errores detectados)
    if overall_status == "requires_human" or critical_errors:
        return {
            "summary": ("Se detectaron errores de ejecución que requieren atención." + debug_msg),
            "risk_notes": ["El sitio puede estar experimentando caídas o errores de código."],
            "recommendation": "Revisar logs y corregir los errores de sintaxis/servidor indicados.",
            "requires_human_attention": True,
            "severity": "critical"
        }

    # 3️⃣ Caso: Advertencias (404s, etc)
    if warning_signals:
        return {
            "summary": ("El sistema está funcionando, pero se detectaron anomalías menores." + debug_msg),
            "risk_notes": ["Archivos faltantes o advertencias de código detectadas."],
            "recommendation": "Verificar rutas de archivos y corregir advertencias para optimizar el sitio.",
            "requires_human_attention": True,
            "severity": "warning"
        }

    # 4️⃣ Caso: listo para ejecutar (todo OK)
    return {
        "summary": "Todo se encuentra funcionando correctamente. No se detectaron anomalías.",
        "risk_notes": [],
        "recommendation": "Continuar con el monitoreo normal.",
        "requires_human_attention": False,
        "severity": "ok"
    }
