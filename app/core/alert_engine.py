# app/core/alert_engine.py
from datetime import datetime, timezone, timedelta

def process_alerts(health_data: dict, last_alert: dict | None = None) -> dict | None:
    """
    Lógica de alertas automáticas con protección contra spam.
    
    🧠 OUTPUT
    {
      "type": "critical",
      "message": "Tu sitio está caído",
      "action": "Revisar contenedor"
    }
    """
    score = health_data.get("score", 100)
    warning_count = health_data.get("warning_count", 0)
    
    # 🔥 SPAM PROTECTION: no repetir alerta en 10 min
    if last_alert:
        last_time_str = last_alert.get("created_at")
        if last_time_str:
            try:
                # Handle potential 'Z' or '+00:00' format
                if last_time_str.endswith("Z"):
                    last_time_str = last_time_str[:-1] + "+00:00"
                last_time = datetime.fromisoformat(last_time_str)
                if last_time.tzinfo is None:
                    last_time = last_time.replace(tzinfo=timezone.utc)
                
                if datetime.now(timezone.utc) - last_time < timedelta(minutes=10):
                    return None
            except Exception:
                # Si falla el parseo, ignoramos el last_alert para no bloquear alertas reales
                pass

    # 🔴 CRÍTICO
    if score < 40:
        return {
            "type": "critical",
            "message": "🚨 Tu sitio está caído",
            "action": "Revisar contenedor"
        }
    
    # 🟡 WARNING
    if score < 70 or warning_count > 10:
        return {
            "type": "warning",
            "message": "⚠ Se detectaron errores en archivos",
            "action": "Ver diagnóstico"
        }
    
    return None
