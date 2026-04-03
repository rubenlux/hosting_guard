"""
Collects real traffic metrics from nginx access logs inside Docker containers.
Runs as a background task every 5 minutes.

How it works:
  docker logs --since 5m <container> → parse nginx combined log format
  → extract status codes → count total / 4xx / 5xx
  → store snapshot in traffic_stats table
"""
import re
import subprocess
import logging
from datetime import datetime

from app.infra.audit.hosting_repository import HostingRepository
from app.infra.audit.metrics_repository import MetricsRepository

logger = logging.getLogger(__name__)

# Matches the HTTP status code in nginx combined log format:
# 127.0.0.1 - - [date] "GET / HTTP/1.1" 200 612 "-" "agent"
#                                         ^^^
_STATUS_RE = re.compile(r'"\s+(\d{3})\s+')

_hosting_repo = HostingRepository()
_metrics_repo = MetricsRepository()


def _parse_logs(raw: str):
    """Returns (total_requests, errors_4xx, errors_5xx) from raw nginx log text."""
    total = errors_4xx = errors_5xx = 0
    for line in raw.splitlines():
        m = _STATUS_RE.search(line)
        if not m:
            continue
        total += 1
        code = int(m.group(1))
        if 400 <= code < 500:
            errors_4xx += 1
        elif code >= 500:
            errors_5xx += 1
    return total, errors_4xx, errors_5xx


def collect_traffic() -> None:
    """
    For every active hosting: pull 5-minute nginx log window, parse, store.
    Called by the background scheduler.
    """
    # Reset thread-local DB connection before each cycle.
    # run_in_executor reuses threads, so the PostgreSQL connection cached from
    # the previous cycle may have been closed server-side after the 5-minute idle.
    from app.infra.audit.sqlite import release_connection
    release_connection()

    hostings = _hosting_repo.get_all_hostings()
    active = [h for h in hostings if h.get("status") == "active"]
    logger.info("traffic_collector: %d active hostings", len(active))

    for hosting in active:
        container = hosting["container_name"]
        try:
            result = subprocess.run(
                ["docker", "logs", "--since", "5m", container],
                capture_output=True,
                text=True,
                timeout=15,
            )
            # nginx writes access logs to stdout, error logs to stderr; combine both
            raw = result.stdout + result.stderr
            total, e4xx, e5xx = _parse_logs(raw)
            _metrics_repo.save_traffic_snapshot(container, total, e4xx, e5xx)
        except subprocess.TimeoutExpired:
            logger.warning("traffic_collector: timeout reading logs for %s", container)
        except Exception as exc:
            logger.error("traffic_collector: error for %s — %s", container, exc)
