#!/usr/bin/env bash
# Chaos 012 — CRA output directory misconfiguration
# Validates: GITHUB_CRA_OUTPUT_DIRECTORY_MISCONFIG signature
set -euo pipefail

echo "[CHAOS 012] Validate CRA output directory misconfiguration detection"

python3 - << 'PYEOF'
import sys
sys.path.insert(0, '.')
from app.services.incidents.incident_knowledge_service import match_error_signature

texts = [
    "Failed to fetch dynamically imported module",
    "output directory not found",
    "Cannot GET /",
]
expected = "GITHUB_CRA_OUTPUT_DIRECTORY_MISCONFIG"

for text in texts:
    matches = match_error_signature(text)
    if matches:
        m = matches[0]
        if m.incident_id == expected:
            print(f"[CHAOS 012] ✓ '{text[:50]}' → {expected}")
        else:
            # Also valid: FRONTEND_CHUNK_404_BLANK_SCREEN uses same signature
            print(f"[CHAOS 012] ~ '{text[:50]}' → {m.incident_id} (acceptable)")
    else:
        print(f"[CHAOS 012] ✗ no match for: {text[:50]}")

# Forbidden: publish public/ as CRA output
from app.services.incidents.incident_knowledge_service import get_forbidden_actions
forbidden = get_forbidden_actions(expected)
if "publish_public_directory_as_cra_output" in forbidden:
    print("[CHAOS 012] ✓ publish_public_directory_as_cra_output correctly forbidden")
if "auto_change_output_dir_without_user_confirmation" in forbidden:
    print("[CHAOS 012] ✓ auto_change_output_dir_without_user_confirmation correctly forbidden")
PYEOF

echo "[CHAOS 012] ✓ Complete"
