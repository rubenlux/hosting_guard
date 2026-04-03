"""
Health checker for hosted containers.
Runs as a background task every 5 minutes.

How it works:
  docker inspect --format "{{.State.Running}}" <container>
  → is_up = (returncode == 0 AND output == "true")
  → response_ms = time taken for inspect call (proxy for container responsiveness)
  → stored in uptime_checks table → used to compute uptime %
"""
import subprocess
import time
import logging

from app.infra.audit.hosting_repository import HostingRepository
from app.infra.audit.metrics_repository import MetricsRepository

logger = logging.getLogger(__name__)

_hosting_repo = HostingRepository()
_metrics_repo = MetricsRepository()


def check_all_hostings() -> None:
    """
    For every non-expired hosting: check container state via docker inspect, record result.
    Called by the background scheduler.
    """
    hostings = _hosting_repo.get_all_hostings()
    # Check all hostings that should be running (skip expired/deleted)
    checkable = [h for h in hostings if h.get("status") not in ("expired", "not_found")]
    logger.info("health_checker: checking %d hostings", len(checkable))

    for hosting in checkable:
        container  = hosting["container_name"]
        hosting_id = hosting["hosting_id"]
        try:
            t0 = time.monotonic()
            result = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Running}}", container],
                capture_output=True,
                text=True,
                timeout=5,
            )
            elapsed_ms = int((time.monotonic() - t0) * 1000)

            is_up = result.returncode == 0 and result.stdout.strip() == "true"
            _metrics_repo.save_uptime_check(
                hosting_id=hosting_id,
                is_up=is_up,
                response_ms=elapsed_ms,
            )
        except subprocess.TimeoutExpired:
            _metrics_repo.save_uptime_check(hosting_id=hosting_id, is_up=False, response_ms=5000)
            logger.warning("health_checker: timeout for %s", container)
        except Exception as exc:
            logger.error("health_checker: error for %s — %s", container, exc)
