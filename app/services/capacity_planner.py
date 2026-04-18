"""
app/services/capacity_planner.py

Capacity Forecast — estimates time-to-exhaustion for CPU, RAM, Disk, and
container slots using a simple linear growth model.

Formula
-------
  growth_rate = usage_now - usage_24h_ago   # percentage points / day
  hours_left  = (100 - usage_now) / (growth_rate / 24)

Current data sources
--------------------
  - CPU / RAM / Disk : placeholder hooks — no node_exporter deployed yet.
                       Replace _get_*_pct() functions when available.
  - Containers       : live count via HostingRepository.get_all_running()

FASE 9 hooks (do not implement now)
------------------------------------
  - Replace _get_cpu_pct / _get_ram_pct / _get_disk_pct with node_exporter
  - Replace _get_*_pct_24h_ago with Prometheus predict_linear queries
  - Wire alert_manager notifications on status == "critical"
"""
import logging
import os
from typing import Optional

from app.infra.audit.hosting_repository import HostingRepository

logger = logging.getLogger(__name__)

# ── Tuneable constants ──────────────────────────────────────────────────────���─
# Maximum container slots before the node is considered saturated.
# Override via env var for different host sizes.
MAX_CONTAINERS: int = int(os.getenv("MAX_CONTAINERS", "50"))


# ── Pluggable resource readers ────────────────────────────────────────────────
# Return float 0-100 or None when data is unavailable.
# Swap these out when node_exporter / psutil metrics become available.

def _get_cpu_pct() -> Optional[float]:
    try:
        import psutil
        return psutil.cpu_percent(interval=0.1)
    except Exception:
        return None


def _get_ram_pct() -> Optional[float]:
    try:
        import psutil
        return psutil.virtual_memory().percent
    except Exception:
        return None


def _get_disk_pct() -> Optional[float]:
    try:
        import psutil
        # Prefer /app/data (mapped to host volume) over container overlay /
        for path in ("/app/data", "/"):
            try:
                return psutil.disk_usage(path).percent
            except Exception:
                continue
        return None
    except Exception:
        return None


def _get_cpu_pct_24h_ago() -> Optional[float]:
    return None  # HOOK: Prometheus predict_linear(rate, 24h)

def _get_ram_pct_24h_ago() -> Optional[float]:
    return None  # HOOK: Prometheus predict_linear(rate, 24h)

def _get_disk_pct_24h_ago() -> Optional[float]:
    return None  # HOOK: Prometheus predict_linear(rate, 24h)


# ── Core forecast logic ───────────────────────────────────────────────────────

def _classify(hours_left: Optional[float]) -> str:
    if hours_left is None:
        return "ok"
    if hours_left < 48:
        return "critical"
    if hours_left < 72:
        return "warning"
    return "ok"


def _compute_resource_forecast(
    usage_now: Optional[float],
    usage_24h_ago: Optional[float],
) -> dict:
    """Return forecast dict for a single resource metric."""
    if usage_now is None:
        return {"usage": None, "hours_left": None, "status": "ok"}

    usage_now = round(usage_now, 1)

    if usage_24h_ago is None:
        return {"usage": usage_now, "hours_left": None, "status": "ok"}

    growth_rate = usage_now - usage_24h_ago

    if growth_rate <= 0:
        return {"usage": usage_now, "hours_left": None, "status": "ok"}

    remaining = 100.0 - usage_now
    if remaining <= 0:
        hours_left = 0.0
    else:
        # growth_rate is percentage points per day; convert to per-hour denominator
        hours_left = round(remaining / (growth_rate / 24), 1)

    return {"usage": usage_now, "hours_left": hours_left, "status": _classify(hours_left)}


def _get_container_forecast() -> dict:
    """Derive container slot usage from the live hosting DB count."""
    try:
        running = HostingRepository().get_all_running()
        current_count = len(running)
    except Exception:
        current_count = 0

    usage_now = round((current_count / MAX_CONTAINERS) * 100, 1) if MAX_CONTAINERS else None
    # No historical container count tracked yet — growth rate unavailable.
    # HOOK: replace None with historical count when time-series storage exists.
    base = _compute_resource_forecast(usage_now, None)
    return {**base, "current": current_count, "max": MAX_CONTAINERS}


# ── Public API ────────────────────────────────────────────────────────────────

def evaluate_capacity_forecast() -> dict:
    """
    Evaluate current capacity trend and return a forecast for each resource.

    Returns
    -------
    {
        "cpu":        {"usage": float|None, "hours_left": float|None, "status": str},
        "ram":        {...},
        "disk":       {...},
        "containers": {"usage": float|None, "hours_left": float|None, "status": str,
                       "current": int, "max": int},
        "recommendation": str | None
    }
    """
    cpu        = _compute_resource_forecast(_get_cpu_pct(),  _get_cpu_pct_24h_ago())
    ram        = _compute_resource_forecast(_get_ram_pct(),  _get_ram_pct_24h_ago())
    disk       = _compute_resource_forecast(_get_disk_pct(), _get_disk_pct_24h_ago())
    containers = _get_container_forecast()

    statuses = [r["status"] for r in (cpu, ram, disk, containers)]

    if "critical" in statuses:
        recommendation = "Upgrade node required within 48h"
    elif "warning" in statuses:
        recommendation = "Monitor closely — scaling likely needed"
    else:
        recommendation = None

    overall = "critical" if "critical" in statuses else ("warning" if "warning" in statuses else "ok")

    # Unified capacity score: worst resource determines the score
    usage_values = [
        r["usage"] for r in (cpu, ram, disk)
        if r.get("usage") is not None
    ]
    if containers.get("usage") is not None:
        usage_values.append(containers["usage"])
    capacity_score = round(max(usage_values), 1) if usage_values else None

    # Days to exhaustion: minimum hours_left across all resources
    hours_left_values = [
        r["hours_left"] for r in (cpu, ram, disk, containers)
        if r.get("hours_left") is not None and r["hours_left"] > 0
    ]
    days_to_exhaustion = round(min(hours_left_values) / 24, 1) if hours_left_values else None

    if overall == "critical":
        recommendation = "scale_now"
    elif overall == "warning":
        recommendation = "monitor"
    else:
        recommendation = "ok"

    logger.info(
        "capacity_forecast",
        extra={
            "cpu_hours_left":        cpu["hours_left"],
            "ram_hours_left":        ram["hours_left"],
            "disk_hours_left":       disk["hours_left"],
            "containers_hours_left": containers["hours_left"],
            "capacity_score":        capacity_score,
            "status":                overall,
        },
    )

    return {
        "cpu":                 cpu,
        "ram":                 ram,
        "disk":                disk,
        "containers":          containers,
        "capacity_score":      capacity_score,
        "overall_status":      overall,
        "days_to_exhaustion":  days_to_exhaustion,
        "recommendation":      recommendation,
    }
