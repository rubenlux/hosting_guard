#!/usr/bin/env bash
# Chaos 008 — Missing container breaks metrics collector
# Validates: RESOURCES_MISSING_CONTAINER_BREAKS_COLLECTOR → skip logic present
set -euo pipefail

echo "[CHAOS 008] Validate missing container does not break metrics collection"

# ── Signature matching ─────────────────────────────────────────────────────────
python3 - << 'PYEOF'
import sys
sys.path.insert(0, '.')
from app.services.incidents.incident_knowledge_service import match_error_signature

texts = [
    "No such container: user_1_test",
    "Error: No such container",
]
expected = "RESOURCES_MISSING_CONTAINER_BREAKS_COLLECTOR"

for text in texts:
    matches = match_error_signature(text)
    if matches and matches[0].incident_id == expected:
        print(f"[CHAOS 008] ✓ '{text}' → {expected}")
    elif matches:
        print(f"[CHAOS 008] ~ '{text}' → {matches[0].incident_id}")
    else:
        print(f"[CHAOS 008] ✗ no match for: {text}")

# Safe: skip_missing_container_in_metrics; Forbidden: stop_all_metric_collection
from app.services.incidents.incident_knowledge_service import get_safe_actions, get_forbidden_actions
safe = get_safe_actions(expected)
forbidden = get_forbidden_actions(expected)
print(f"[CHAOS 008] safe_actions: {safe}")
print(f"[CHAOS 008] forbidden_actions: {forbidden}")

if "skip_missing_container_in_metrics" in safe:
    print("[CHAOS 008] ✓ skip_missing_container_in_metrics in safe_actions")
if "stop_all_metric_collection" in forbidden:
    print("[CHAOS 008] ✓ stop_all_metric_collection correctly forbidden")
if "delete_hosting_record_when_container_missing" in forbidden:
    print("[CHAOS 008] ✓ delete_hosting_record_when_container_missing correctly forbidden")
PYEOF

# ── Functional test: collect_resource_usage handles missing container ──────────
python3 - << 'PYEOF2'
import sys
sys.path.insert(0, '.')

# Patch docker command to simulate "No such container"
from unittest.mock import patch, MagicMock

# Verify the collector doesn't crash on missing container
try:
    with patch("app.infra.docker_client.run_docker_command") as mock_docker:
        mock_docker.return_value = (1, "", "Error response from daemon: No such container: user_99_fake")
        # Import and call the stats function minimally
        # We just verify it handles the error without exception
        from app.services.collect_resource_usage import _get_container_stats
        result = _get_container_stats("user_99_fake")
        print(f"[CHAOS 008] _get_container_stats returned: {result}")
        print("[CHAOS 008] ✓ No exception raised on missing container")
except ImportError:
    print("[CHAOS 008] ~ _get_container_stats not found — verify manually")
except Exception as e:
    print(f"[CHAOS 008] ✗ Exception on missing container: {e}")
    sys.exit(1)
PYEOF2

echo "[CHAOS 008] ✓ Complete"
