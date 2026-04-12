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

def process_alerts(health_result: Dict, last_alert: Optional[Dict] = None) -> Optional[Dict]:
    """
    Evalúa si se debe generar una nueva alerta basada en el resultado de salud.
    Evita duplicados si la alerta es la misma que la anterior.
    """
    score = health_result["score"]
    alert = check_alerts(score)
    
    if not alert:
        return None
        
    # Evitar spam: si la alerta es idéntica a la última guardada, no la repetimos.
    # last_alert viene de site_health_history → el campo es "alert_message", no "message".
    if last_alert and last_alert.get("alert_message") == alert["message"]:
        return None
        
    return alert
