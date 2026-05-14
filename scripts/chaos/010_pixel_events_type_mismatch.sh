#!/usr/bin/env bash
# Chaos 010 — Pixel events type mismatch (text = integer)
# Validates: ADMIN_TERMINATE_PIXEL_EVENTS_TYPE_MISMATCH signature
set -euo pipefail

echo "[CHAOS 010] Validate pixel events type mismatch detection"

python3 - << 'PYEOF'
import sys
sys.path.insert(0, '.')
from app.services.incidents.incident_knowledge_service import match_error_signature

texts = [
    "operator does not exist: text = integer",
    "ProgrammingError: operator does not exist",
]
expected = "ADMIN_TERMINATE_PIXEL_EVENTS_TYPE_MISMATCH"

for text in texts:
    matches = match_error_signature(text)
    if matches and matches[0].incident_id == expected:
        print(f"[CHAOS 010] ✓ '{text}' → {expected}")
    elif matches:
        print(f"[CHAOS 010] ~ '{text}' → {matches[0].incident_id}")
    else:
        print(f"[CHAOS 010] ✗ no match for: {text}")
PYEOF

echo "[CHAOS 010] ✓ Complete"
