"""
Tests for app/services/capacity_planner.py

All tests mock HostingRepository and the pluggable resource readers so they
run without a real DB or node_exporter.
"""
from unittest.mock import patch, MagicMock
from app.services.capacity_planner import (
    _compute_resource_forecast,
    _classify,
    evaluate_capacity_forecast,
    MAX_CONTAINERS,
)


# ── _classify ─────────────────────────────────────────────────────────────────

def test_classify_none_is_ok():
    assert _classify(None) == "ok"

def test_classify_below_48h_is_critical():
    assert _classify(0.0)  == "critical"
    assert _classify(10.0) == "critical"
    assert _classify(47.9) == "critical"

def test_classify_48_to_72_is_warning():
    assert _classify(48.0) == "warning"
    assert _classify(71.9) == "warning"

def test_classify_72h_and_above_is_ok():
    assert _classify(72.0) == "ok"
    assert _classify(999.0) == "ok"


# ── _compute_resource_forecast ────────────────────────────────────────────────

def test_positive_growth_computes_hours_left():
    result = _compute_resource_forecast(usage_now=50.0, usage_24h_ago=26.0)
    # growth_rate = 24.0 pp/day
    # hours_left = (100 - 50) / (24 / 24) = 50 / 1 = 50.0h → "warning"
    assert result["usage"] == 50.0
    assert result["hours_left"] == 50.0
    assert result["status"] == "warning"

def test_zero_growth_returns_none_hours():
    result = _compute_resource_forecast(usage_now=60.0, usage_24h_ago=60.0)
    assert result["hours_left"] is None
    assert result["status"] == "ok"

def test_negative_growth_returns_none_hours():
    result = _compute_resource_forecast(usage_now=40.0, usage_24h_ago=55.0)
    assert result["hours_left"] is None
    assert result["status"] == "ok"

def test_no_24h_ago_data_returns_none_hours():
    result = _compute_resource_forecast(usage_now=80.0, usage_24h_ago=None)
    assert result["usage"] == 80.0
    assert result["hours_left"] is None
    assert result["status"] == "ok"

def test_no_current_data_returns_none():
    result = _compute_resource_forecast(usage_now=None, usage_24h_ago=None)
    assert result["usage"] is None
    assert result["hours_left"] is None
    assert result["status"] == "ok"

def test_safe_division_at_100_percent():
    # usage_now already at 100% with positive growth → hours_left = 0
    result = _compute_resource_forecast(usage_now=100.0, usage_24h_ago=80.0)
    assert result["hours_left"] == 0.0
    assert result["status"] == "critical"

def test_critical_below_48h():
    # growth = 10 pp/day → hours_left = (100-90) / (10/24) = 10 / 0.417 ≈ 24h
    result = _compute_resource_forecast(usage_now=90.0, usage_24h_ago=80.0)
    assert result["status"] == "critical"
    assert result["hours_left"] is not None
    assert result["hours_left"] < 48

def test_ok_above_72h():
    # growth = 1 pp/day → hours_left = (100-10) / (1/24) = 90 * 24 = 2160h
    result = _compute_resource_forecast(usage_now=10.0, usage_24h_ago=9.0)
    assert result["status"] == "ok"
    assert result["hours_left"] > 72


# ── evaluate_capacity_forecast ────────────────────────────────────────────────

def _patch_all_readers(cpu=None, ram=None, disk=None,
                       cpu_ago=None, ram_ago=None, disk_ago=None,
                       running_count=0):
    """Return a list of patch context managers for all resource readers."""
    import app.services.capacity_planner as _cp
    mock_repo = MagicMock()
    mock_repo.get_all_running.return_value = [{}] * running_count
    return [
        patch.object(_cp, "_get_cpu_pct",         return_value=cpu),
        patch.object(_cp, "_get_ram_pct",         return_value=ram),
        patch.object(_cp, "_get_disk_pct",        return_value=disk),
        patch.object(_cp, "_get_cpu_pct_24h_ago", return_value=cpu_ago),
        patch.object(_cp, "_get_ram_pct_24h_ago", return_value=ram_ago),
        patch.object(_cp, "_get_disk_pct_24h_ago",return_value=disk_ago),
        patch.object(_cp, "HostingRepository",    return_value=mock_repo),
    ]


def test_evaluate_all_placeholders_returns_ok():
    """With no real metrics yet, every resource is 'ok'."""
    patches = _patch_all_readers()
    # Use contextlib.ExitStack to apply multiple patches
    from contextlib import ExitStack
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        result = evaluate_capacity_forecast()

    assert result["cpu"]["status"]        == "ok"
    assert result["ram"]["status"]        == "ok"
    assert result["disk"]["status"]       == "ok"
    assert result["containers"]["status"] == "ok"
    assert result["recommendation"]       is None


def test_evaluate_recommendation_critical_when_cpu_critical():
    from contextlib import ExitStack
    # CPU at 90%, was at 70% 24h ago → growth 20/day → hours_left = (10) / (20/24) = 12h → critical
    patches = _patch_all_readers(cpu=90.0, cpu_ago=70.0)
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        result = evaluate_capacity_forecast()

    assert result["cpu"]["status"] == "critical"
    assert result["recommendation"] == "Upgrade node required within 48h"


def test_evaluate_recommendation_warning_when_ram_warning():
    from contextlib import ExitStack
    # RAM at 50%, was at 26% 24h ago → growth 24/day → hours_left = 50h → warning
    patches = _patch_all_readers(ram=50.0, ram_ago=26.0)
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        result = evaluate_capacity_forecast()

    assert result["ram"]["status"] == "warning"
    assert result["recommendation"] == "Monitor closely — scaling likely needed"


def test_evaluate_containers_reflect_current_count():
    from contextlib import ExitStack
    patches = _patch_all_readers(running_count=5)
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        result = evaluate_capacity_forecast()

    assert result["containers"]["current"] == 5
    assert result["containers"]["max"]     == MAX_CONTAINERS
    expected_usage = round(5 / MAX_CONTAINERS * 100, 1)
    assert result["containers"]["usage"]   == expected_usage


def test_evaluate_critical_overrides_warning():
    """When both RAM is warning and CPU is critical, recommendation is critical."""
    from contextlib import ExitStack
    patches = _patch_all_readers(
        cpu=95.0, cpu_ago=71.0,   # hours_left ≈ 6h → critical
        ram=50.0, ram_ago=26.0,   # hours_left ≈ 50h → warning
    )
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        result = evaluate_capacity_forecast()

    assert result["recommendation"] == "Upgrade node required within 48h"


def test_evaluate_never_raises_on_repo_failure():
    """evaluate_capacity_forecast is safe even when DB raises."""
    import app.services.capacity_planner as _cp
    with patch.object(_cp, "_get_cpu_pct",          return_value=None), \
         patch.object(_cp, "_get_ram_pct",          return_value=None), \
         patch.object(_cp, "_get_disk_pct",         return_value=None), \
         patch.object(_cp, "_get_cpu_pct_24h_ago",  return_value=None), \
         patch.object(_cp, "_get_ram_pct_24h_ago",  return_value=None), \
         patch.object(_cp, "_get_disk_pct_24h_ago", return_value=None), \
         patch.object(_cp, "HostingRepository",     side_effect=Exception("DB down")):
        result = evaluate_capacity_forecast()

    # containers falls back to count=0 on exception
    assert result["containers"]["current"] == 0
    assert result["recommendation"] is None
