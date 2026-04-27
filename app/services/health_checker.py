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
from app.services.notification_service import notify

logger = logging.getLogger(__name__)

_hosting_repo = HostingRepository()
_metrics_repo = MetricsRepository()
_health_repo = HealthRepository()

_CPU_WARN_THRESHOLD = 85.0
_RAM_WARN_THRESHOLD = 90.0

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
    from app.infra.db import reset_pg_connection
    reset_pg_connection()

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

            # 4a. Snapshot of previous state — needed for recovery detection below.
            # Must be fetched BEFORE saving the new entry this cycle.
            previous_health = _health_repo.get_latest_health(hosting_id)

            # 4b. Alert Engine — dedup handled inside process_alerts
            last_alert = _health_repo.get_last_alert(hosting_id)
            alert = process_alerts(health_result, last_alert)

            site_name = hosting.get("name") or container

            if alert:
                _health_repo.create_alert(
                    user_id=user_id,
                    site_id=hosting_id,
                    level="warning" if health_result["status"] == "warning" else "critical",
                    message=alert["message"]
                )
                # Notify user — site down vs performance alert
                if not is_up:
                    notify(
                        user_id,
                        f"Sitio caído: {site_name}",
                        f"El contenedor de '{site_name}' no está activo. "
                        f"Revisá el estado desde el panel.",
                        category="hosting", severity="critical", channel="both",
                        action_url="/dashboard",
                    )
                elif alert["type"] == "critical":
                    notify(
                        user_id,
                        f"Error crítico en {site_name}",
                        alert["message"],
                        category="hosting", severity="critical", channel="both",
                        action_url="/dashboard",
                    )
                elif alert["type"] == "warning":
                    cpu, ram = stats["cpu"], stats["ram"]
                    if cpu > _CPU_WARN_THRESHOLD or ram > _RAM_WARN_THRESHOLD:
                        notify(
                            user_id,
                            f"Recursos altos: {site_name}",
                            f"Tu sitio '{site_name}' usó CPU {cpu:.0f}% y RAM {ram:.0f}% "
                            f"en el último ciclo de monitoreo.",
                            category="performance", severity="warning", channel="both",
                            action_url="/dashboard",
                        )
                    else:
                        notify(
                            user_id,
                            f"Alerta de rendimiento: {site_name}",
                            alert["message"],
                            category="hosting", severity="warning", channel="dashboard",
                            action_url="/dashboard",
                        )

            # 4c. Recovery detection — fires exactly once on the bad → good transition.
            # previous_health.alert_type is set on cycles that triggered an alert.
            # Once this cycle saves a clean entry (alert_type=None), the next cycle
            # will see alert_type=None and skip the recovery event.
            is_now_healthy = (
                health_result.get("status") in ("excellent", "good")
                and health_result.get("error_count", 0) == 0
                and not alert
            )
            previous_was_bad = (
                previous_health
                and previous_health.get("alert_type") in ["critical", "warning"]
            )
            if is_now_healthy and previous_was_bad:
                # Resolve all open critical/warning alerts for this site
                resolved_count = _health_repo.resolve_open_alerts(hosting_id)
                if resolved_count:
                    logger.info(
                        "health_checker: resolved %d alert(s) for hosting_id=%s (recovery)",
                        resolved_count, hosting_id,
                    )
                # Create a recovery event so the dashboard shows the transition
                _health_repo.create_alert(
                    user_id=user_id,
                    site_id=hosting_id,
                    level="recovery",
                    message="El sitio se ha estabilizado. Los errores han sido resueltos.",
                )
                notify(
                    user_id,
                    f"Sitio recuperado: {site_name}",
                    f"'{site_name}' volvió a funcionar correctamente.",
                    category="hosting", severity="success", channel="both",
                    action_url="/dashboard",
                )

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

            # 6. Log resource snapshot so admin panel "Jobs & Errores" and
            #    "Top Tenants por Recursos" have data to query.
            _hosting_repo.log_orchestrator_event(
                container, user_id, "health_check",
                f"score={health_result['score']} cpu={stats['cpu']}% ram={stats['ram']}%",
                cpu_pct=stats["cpu"], mem_pct=stats["ram"], simulated=False,
            )

        except Exception as exc:
            logger.error("health_checker: failed for %s — %s", container, exc)

    logger.info("health_checker: cycle finished")
