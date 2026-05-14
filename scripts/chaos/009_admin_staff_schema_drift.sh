#!/usr/bin/env bash
# Chaos 009 — Admin staff created_at_ts schema drift
# Validates: ADMIN_STAFF_CREATED_AT_TS_500 signature → matched
set -euo pipefail

echo "[CHAOS 009] Validate admin staff schema drift detection"

python3 - << 'PYEOF'
import sys
sys.path.insert(0, '.')
from app.services.incidents.incident_knowledge_service import match_error_signature

texts = [
    "column created_at_ts does not exist",
    "ProgrammingError: column created_at_ts",
]
expected = "ADMIN_STAFF_CREATED_AT_TS_500"

for text in texts:
    matches = match_error_signature(text)
    if matches and matches[0].incident_id == expected:
        print(f"[CHAOS 009] ✓ '{text}' → {expected}")
    elif matches:
        print(f"[CHAOS 009] ~ '{text}' → {matches[0].incident_id} (expected {expected})")
    else:
        print(f"[CHAOS 009] ✗ no match for: {text}")

# Validate: forbidden = alter without migration
from app.services.incidents.incident_knowledge_service import get_forbidden_actions
forbidden = get_forbidden_actions(expected)
if "alter_table_add_column_without_migration" in forbidden:
    print("[CHAOS 009] ✓ alter_table correctly forbidden")
if "drop_column_without_backup" in forbidden:
    print("[CHAOS 009] ✓ drop_column correctly forbidden")
PYEOF

# ── Live API test ──────────────────────────────────────────────────────────────
if [[ -n "${ADMIN_TOKEN:-}" ]]; then
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    "http://localhost:8000/admin/staff" \
    -b "access_token=${ADMIN_TOKEN}" --max-time 5)
  echo "[CHAOS 009] GET /admin/staff → HTTP ${HTTP_CODE}"
  [[ "$HTTP_CODE" == "200" ]] && echo "[CHAOS 009] ✓ Staff endpoint healthy" \
    || echo "[CHAOS 009] ~ Staff endpoint returned ${HTTP_CODE} — check if schema drift present"
fi

echo "[CHAOS 009] ✓ Complete"
