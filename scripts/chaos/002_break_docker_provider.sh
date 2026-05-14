#!/usr/bin/env bash
# Chaos 002 — Simulate Docker provider failure signature in logs
# Validates: TRAEFIK_DOCKER_PROVIDER_UNHEALTHY / TRAEFIK_CLIENT_VERSION_TOO_OLD
# NOTE: This does NOT actually break Traefik — it injects a synthetic log entry
# and validates that the signature matcher detects it correctly.
set -euo pipefail

echo "[CHAOS 002] Simulate Docker provider error signature"

SYNTHETIC_LOG="time=\"2026-05-14T00:00:00Z\" level=error msg=\"client version 1.24 is too old. Minimum version required is 1.41\""

echo "[CHAOS 002] Injecting synthetic log: ${SYNTHETIC_LOG}"

# Test signature matching via the knowledge service
python3 - << 'PYEOF'
import sys
sys.path.insert(0, '.')
from app.services.incidents.incident_knowledge_service import match_error_signature

text = 'client version 1.24 is too old. Minimum version required is 1.41'
matches = match_error_signature(text)

if not matches:
    print("[CHAOS 002] ✗ No runbook matched — signature detection FAILED")
    sys.exit(1)

best = matches[0]
print(f"[CHAOS 002] ✓ Matched runbook: {best.incident_id}")
print(f"[CHAOS 002] ✓ Confidence: {best.confidence}")
print(f"[CHAOS 002] ✓ Match method: {best.match_method}")
print(f"[CHAOS 002] ✓ Auto-repair allowed: {best.auto_repair_allowed}")
print(f"[CHAOS 002] ✓ Safe actions: {best.safe_actions}")
print(f"[CHAOS 002] ✓ Forbidden actions: {best.forbidden_actions}")

expected_id = "TRAEFIK_CLIENT_VERSION_TOO_OLD"
if best.incident_id == expected_id:
    print(f"[CHAOS 002] ✓ Correct runbook ID: {expected_id}")
else:
    print(f"[CHAOS 002] ✗ Expected {expected_id} but got {best.incident_id}")
    sys.exit(1)

# Validate forbidden actions are not in safe actions
forbidden = set(best.forbidden_actions)
safe = set(best.safe_actions)
overlap = forbidden & safe
if overlap:
    print(f"[CHAOS 002] ✗ CRITICAL: forbidden actions overlap with safe actions: {overlap}")
    sys.exit(1)
print("[CHAOS 002] ✓ No overlap between safe and forbidden actions")
PYEOF

echo "[CHAOS 002] ✓ Signature detection validated (no Traefik restart needed)"
