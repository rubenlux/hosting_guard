# app/core/health_engine.py

def calculate_health_score(data: dict) -> dict:
    """
    Calcula el score de salud de un sitio basado en su estado actual.
    
    🧠 INPUT
    {
      "container_status": "running",
      "cpu": 10,
      "ram": 30,
      "errors": [
        {"type": "http_404", "count": 12},
        {"type": "php_fatal", "count": 1}
      ]
    }
    """
    score = 100
    status = "good"
    color = "green"
    error_count = 0
    warning_count = 0

    container_status = str(data.get("container_status", "unknown")).strip().lower()
    cpu = data.get("cpu", 0)
    ram = data.get("ram", 0)
    errors = data.get("errors", [])

    # 🔴 CRÍTICO: Contenedor no está corriendo
    if not container_status or container_status not in ("running", "up"):
        score = 0
        error_count = 1  # contenedor caído = error crítico
        status = "down"
        color = "red"
        return {
            "score": score,
            "status": status,
            "color": color,
            "error_count": error_count,
            "warning_count": warning_count,
        }
    else:
        # 🟠 CPU
        if cpu > 85:
            score -= 20
        
        # 🟠 RAM
        if ram > 80:
            score -= 15

        # 🟡 404 y Errores Graves
        for err in errors:
            # Probes externos (bots/scanners) no afectan el health score
            if err.get("source") == "external_probe":
                continue

            err_type = err.get("type", "").lower()
            count = err.get("count", 0)

            if "http_404" in err_type and count > 10:
                score -= 10
                warning_count += count

            if "php_fatal" in err_type:
                score -= 50
                error_count += count

            if "db_error" in err_type or "database_error" in err_type:
                score -= 70
                error_count += count

    # Limitar score entre 0 y 100
    score = max(0, min(100, score))

    # 🧠 CLASIFICACIÓN
    if score >= 90:
        status = "excellent" # 🟢 excelente
        color = "green"
    elif score >= 70:
        status = "good" # 🟡 estable
        color = "yellow"
    elif score >= 40:
        status = "warning" # 🟠 warning
        color = "orange"
    else:
        status = "critical" # 🔴 crítico
        color = "red"

    return {
        "score": score,
        "status": status,
        "color": color,
        "error_count": error_count,
        "warning_count": warning_count
    }
