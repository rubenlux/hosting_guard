# app/core/ai_advisory.py

from typing import Any, Dict


def generate_ai_advice(decision_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Capa de asesoría de IA (Simulada para v1.0).
    Observa el resultado del pipeline y genera explicaciones/recomendaciones humanas.
    En versiones futuras, aquí se integra el RAG y el modelo de lenguaje.
    """

    diagnosis = decision_result.get("diagnosis", {})
    overall_status = decision_result.get("overall_status")
    confidence = diagnosis.get("confidence_level")

    # Generamos una base de consejo según el diagnóstico
    advice = {
        "human_summary": "Estamos analizando la situación técnica de su sitio.",
        "technical_context": "Análisis basado en patrones de comportamiento conocidos.",
        "confidence_context": "Nivel de certeza actual: " + str(confidence),
        "recommendations": [],
    }

    # Caso: Error en Ecommerce post-deploy (Regla de negocio crítica)
    if decision_result.get("project_type") == "ecommerce" and any(
        c["cause_code"] == "checkout_failure_after_deploy" for c in diagnosis.get("probable_causes", [])
    ):
        advice["human_summary"] = (
            "Detectamos un fallo crítico en el proceso de compra justo después de los últimos cambios."
        )
        advice["technical_context"] = (
            "Este patrón coincide con incidencias previas donde un deploy afectó la pasarela de pagos."
        )
        advice["recommendations"] = [
            "Recomendamos revertir el despliegue inmediatamente para restaurar las ventas.",
            "Una vez restaurado, verifique los logs de la pasarela de pagos en el entorno de pruebas.",
        ]

    # Caso: Error 500 post-plugin update
    elif any(c["cause_code"] == "plugin_incompatibility" for c in diagnosis.get("probable_causes", [])):
        advice["human_summary"] = (
            "Su sitio muestra un error interno que parece haber sido causado por la "
            "reciente actualización de un plugin."
        )
        advice["technical_context"] = (
            "Las incompatibilidades de plugins son la causa más común de errores 500 en WordPress tras cambios."
        )
        advice["recommendations"] = [
            "La acción más segura es revertir el cambio del plugin específico.",
            "Si el error persiste, será necesario revisar los logs de errores de PHP.",
        ]

    # Caso: Desconocido (Unknown)
    elif overall_status == "unknown":
        advice["human_summary"] = "No logramos identificar la causa raíz exacta con los datos actuales."
        advice["technical_context"] = "El síntoma no coincide con patrones de fallo predefinidos de alta confianza."
        advice["recommendations"] = [
            "No se recomiendan acciones automáticas por precaución.",
            "Un técnico senior debe revisar los logs del servidor manualmente.",
        ]

    return advice
