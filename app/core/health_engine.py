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

    🧠 OUTPUT (added in v2)
      score_breakdown: dict of individual penalties applied, e.g.
        {"cpu_penalty": -20, "ram_penalty": -15, "errors_penalty": -50}
      Useful for LLM context — lets the model reason about *why* the score
      is what it is, not just the final number.
    """
    score         = 100
    status        = "good"
    color         = "green"
    error_count   = 0
    warning_count = 0
    breakdown     = {}

    container_status = str(data.get("container_status", "unknown")).strip().lower()
    cpu    = data.get("cpu",    0)
    ram    = data.get("ram",    0)
    errors = data.get("errors", [])

    # 🔴 CRÍTICO: Contenedor no está corriendo
    if not container_status or container_status not in ("running", "up"):
        score       = 0
        error_count = 1
        status      = "down"
        color       = "red"
        breakdown["container_penalty"] = -100
        return {
            "score":           score,
            "status":          status,
            "color":           color,
            "error_count":     error_count,
            "warning_count":   warning_count,
            "score_breakdown": breakdown,
        }

    # 🟠 CPU
    if cpu > 85:
        score -= 20
        breakdown["cpu_penalty"] = -20

    # 🟠 RAM
    if ram > 80:
        score -= 15
        breakdown["ram_penalty"] = -15

    # 🟡 404 y Errores Graves
    for err in errors:
        # Probes externos (bots/scanners) no afectan el health score
        if err.get("source") == "external_probe":
            continue

        err_type = err.get("type", "").lower()
        count    = err.get("count", 0)

        if "http_404" in err_type and count > 10:
            score -= 10
            warning_count += count
            breakdown["http_404_penalty"] = breakdown.get("http_404_penalty", 0) - 10

        if "php_fatal" in err_type:
            score -= 50
            error_count += count
            breakdown["errors_penalty"] = breakdown.get("errors_penalty", 0) - 50

        if "db_error" in err_type or "database_error" in err_type:
            score -= 70
            error_count += count
            breakdown["errors_penalty"] = breakdown.get("errors_penalty", 0) - 70

    # Limitar score entre 0 y 100
    score = max(0, min(100, score))

    # 🧠 CLASIFICACIÓN
    if score >= 90:
        status = "excellent"
        color  = "green"
    elif score >= 70:
        status = "good"
        color  = "yellow"
    elif score >= 40:
        status = "warning"
        color  = "orange"
    else:
        status = "critical"
        color  = "red"

    return {
        "score":           score,
        "status":          status,
        "color":           color,
        "error_count":     error_count,
        "warning_count":   warning_count,
        "score_breakdown": breakdown,
    }
