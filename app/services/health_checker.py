"""
Health checker for hosted containers with Scoring and Alerts.
Runs as a background task every 5 minutes.
"""
import subprocess
import time
import logging
from datetime import datetime, timezone

from app.infra.audit.hosting_repository import HostingRepository
from app.infra.audit.metrics_repository import MetricsRepository
from app.infra.audit.health_repository import HealthRepository
from app.core.health_engine import calculate_health_score
from app.core.alert_engine import process_alerts

logger = logging.getLogger(__name__)

_hosting_repo = HostingRepository()
_metrics_repo = MetricsRepository()
_health_repo = HealthRepository()

def _get_docker_stats(container_name: str) -> dict:
    """Obtiene CPU y RAM real de un contenedor."""
    try:
        result = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{.CPUPerc}}|{{.MemPerc}}", container_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split("|")
            if len(parts) >= 2:
                cpu = float(parts[0].replace("%", ""))
                ram = float(parts[1].replace("%", ""))
                return {"cpu": cpu, "ram": ram}
    except Exception:
        pass
    return {"cpu": 0.0, "ram": 0.0}

def _get_recent_errors(container_name: str) -> list:
    """Analiza logs recientes en busca de errores graves."""
    errors = []
    try:
        # Errores HTTP de nginx (vía traffic_stats)
        stats = _metrics_repo.get_traffic_stats(container_name, hours=1)
        if stats.get("errors_4xx", 0) > 10:
            errors.append({"type": "http_404", "count": stats["errors_4xx"]})
        if stats.get("errors_5xx", 0) > 0:
            errors.append({"type": "http_5xx", "count": stats["errors_5xx"]})

        # Errores críticos en logs
        res = subprocess.run(
            ["docker", "logs", "--since", "5m", container_name],
            capture_output=True, text=True, timeout=5
        )
        logs = (res.stdout + res.stderr).lower()
        if "php fatal error" in logs:
            errors.append({"type": "php_fatal", "count": logs.count("php fatal error")})
        if "database error" in logs or "error connecting to database" in logs:
            errors.append({"type": "db_error", "count": 1})
            
    except Exception:
        pass
    return errors

def check_all_hostings() -> None:
    """
    Ejecuta el ciclo de salud completo: 
    Uptime -> Stats -> Scoring -> Alerts -> Persistencia
    """
    from app.infra.audit.sqlite import release_connection
    release_connection()

    hostings = _hosting_repo.get_all_hostings()
    checkable = [h for h in hostings if h.get("status") not in ("expired", "not_found")]
    logger.info("health_checker: starting cycle for %d sites", len(checkable))

    for hosting in checkable:
        container  = hosting["container_name"]
        hosting_id = hosting["hosting_id"]
        user_id    = hosting["user_id"]
        
        try:
            # 1. Uptime Check (Legacy compatible)
            t0 = time.monotonic()
            res_inspect = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Status}}", container],
                capture_output=True, text=True, timeout=5,
            )
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            status = res_inspect.stdout.strip() if res_inspect.returncode == 0 else "exited"
            is_up = (status == "running")
            
            _metrics_repo.save_uptime_check(hosting_id=hosting_id, is_up=is_up, response_ms=elapsed_ms)

            # 2. Collect Extended Metrics
            stats = _get_docker_stats(container)
            errors = _get_recent_errors(container)

            # 3. Calculation Engine
            health_input = {
                "container_status": status,
                "cpu": stats["cpu"],
                "ram": stats["ram"],
                "errors": errors
            }
            health_result = calculate_health_score(health_input)

            # 4. Alert Engine
            last_alert = _health_repo.get_last_alert(hosting_id)
            alert = process_alerts(health_result, last_alert)

            # 5. Persistencia Histórica
            _health_repo.save_health_entry(
                user_id=user_id,
                site_id=hosting_id,
                score=health_result["score"],
                status=health_result["status"],
                cpu=stats["cpu"],
                ram=stats["ram"],
                error_count=health_result["error_count"],
                warning_count=health_result["warning_count"],
                alert_type=alert["type"] if alert else None,
                alert_message=alert["message"] if alert else None
            )

        except Exception as exc:
            logger.error("health_checker: failed for %s — %s", container, exc)

    logger.info("health_checker: cycle finished")
