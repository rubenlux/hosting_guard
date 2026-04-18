"""
Background job: polls Prometheus /api/v1/alerts every 60 seconds and persists
firing alerts to system_alert_events via SystemAlertRepository.

This is the authoritative source for /health/system alerts — the dashboard
shows what Prometheus decided, not UI-computed heuristics.
"""
import logging
import os
from typing import Dict, Optional

import requests

from app.infra.audit.system_alert_repository import SystemAlertRepository

logger = logging.getLogger(__name__)

_PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
_repo = SystemAlertRepository()

# Maps alert name → component label for alerts that don't carry one in labels
_COMPONENT_MAP: Dict[str, str] = {
    "NodeCPUWarning":       "cpu",
    "NodeCPUCritical":      "cpu",
    "NodeRAMWarning":       "ram",
    "NodeRAMCritical":      "ram",
    "NodeDiskWarning":      "disk",
    "NodeDiskCritical":     "disk",
    "DiskSpaceHigh":        "disk",
    "DBHighErrorRate":      "database",
    "DBPoolNearExhaustion": "database",
    "SiteHealthZero":       "hosting",
    "ContainerExited":      "hosting",
    "ZombieContainerDetected": "hosting",
    "APILatencyHigh":       "api",
    "AppDown":              "app",
}


def _component_for(alert_name: str, labels: Dict) -> str:
    if labels.get("component"):
        return labels["component"]
    return _COMPONENT_MAP.get(alert_name, "system")


def poll_prometheus_alerts() -> None:
    """Fetch firing alerts from Prometheus and sync with system_alert_events table."""
    try:
        resp = requests.get(
            f"{_PROMETHEUS_URL}/api/v1/alerts",
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("prometheus_alert_poller: could not reach Prometheus: %s", exc)
        return

    alerts = data.get("data", {}).get("alerts", [])
    firing_names: set = set()

    for alert in alerts:
        if alert.get("state") != "firing":
            continue

        labels: Dict = alert.get("labels", {})
        annotations: Dict = alert.get("annotations", {})

        alert_name: str = labels.get("alertname", "unknown")
        severity: str = labels.get("severity", "warning")
        component: str = _component_for(alert_name, labels)
        message: str = annotations.get("summary") or annotations.get("description") or alert_name

        try:
            _repo.upsert_firing_alert(
                alert_name=alert_name,
                severity=severity,
                component=component,
                message=message,
                labels=labels,
            )
        except Exception as exc:
            logger.error("prometheus_alert_poller: upsert failed for %s: %s", alert_name, exc)

        firing_names.add(alert_name)

    try:
        resolved = _repo.resolve_alerts_not_in(firing_names)
        if resolved:
            logger.info("prometheus_alert_poller: resolved %d alerts no longer firing", resolved)
    except Exception as exc:
        logger.error("prometheus_alert_poller: resolve_alerts_not_in failed: %s", exc)

    logger.debug(
        "prometheus_alert_poller: %d firing alerts synced (%s)",
        len(firing_names),
        ", ".join(sorted(firing_names)) if firing_names else "none",
    )
