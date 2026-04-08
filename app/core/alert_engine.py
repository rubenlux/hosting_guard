# app/core/alert_engine.py
from typing import Optional, Dict

def check_alerts(score: int) -> Optional[Dict[str, str]]:
    """
    Evalúa el score de salud y decide si se debe disparar una alerta.
    
    🎯 LÓGICA
    score < 40 -> critical
    score < 70 -> warning
    """
    if score < 40:
        return {
            "type": "critical",
            "message": "Tu sitio está caído o extremadamente inestable (Salud < 40)"
        }

    if score < 70:
        return {
            "type": "warning",
            "message": "Se detectaron problemas de rendimiento o errores menores en el sitio (Salud < 70)"
        }

    return None
