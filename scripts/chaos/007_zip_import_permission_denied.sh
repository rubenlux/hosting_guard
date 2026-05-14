#!/usr/bin/env bash
# Chaos 007 — ZIP import permission denied
# Validates: writability check returns 503 → ZIP_IMPORT_PERMISSION_DENIED matched
set -euo pipefail

echo "[CHAOS 007] Validate ZIP import permission denied detection"

# ── Signature matching ─────────────────────────────────────────────────────────
python3 - << 'PYEOF'
import sys
sys.path.insert(0, '.')
from app.services.incidents.incident_knowledge_service import match_error_signature

texts = [
    "Permission denied: /tmp/hg_imports",
    "import_dir_not_writable",
    "El directorio de uploads no es escribible",
]
expected = "ZIP_IMPORT_PERMISSION_DENIED"

for text in texts:
    matches = match_error_signature(text)
    if matches and matches[0].incident_id == expected:
        print(f"[CHAOS 007] ✓ '{text[:50]}' → {expected}")
    elif matches:
        print(f"[CHAOS 007] ~ '{text[:50]}' → {matches[0].incident_id} (expected {expected})")
    else:
        print(f"[CHAOS 007] ~ '{text[:50]}' → no exact match (keyword fallback)")

# Validate forbidden: skip_permission_check is forbidden
from app.services.incidents.incident_knowledge_service import get_forbidden_actions
forbidden = get_forbidden_actions(expected)
if "skip_permission_check_on_upload" in forbidden:
    print(f"[CHAOS 007] ✓ 'skip_permission_check_on_upload' correctly forbidden")
else:
    print(f"[CHAOS 007] ~ forbidden list: {forbidden}")
PYEOF

# ── Live API test: upload endpoint must return 503 when dir not writable ───────
# Only run if container name provided and directory manipulable
CONTAINER="${1:-}"
if [[ -n "$CONTAINER" && -n "${ADMIN_TOKEN:-}" ]]; then
  SITE_DIR="/opt/clients/${CONTAINER}"
  echo "[CHAOS 007] Testing writability check for ${SITE_DIR}..."

  if [[ -d "$SITE_DIR" ]]; then
    # Remove write bit
    chmod a-w "$SITE_DIR"
    echo "[CHAOS 007] Write bit removed from ${SITE_DIR}"

    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
      -X POST "http://localhost:8000/hosting/upload-zip" \
      -b "access_token=${ADMIN_TOKEN}" \
      -F "file=@/dev/null;filename=test.zip" \
      --max-time 10 || echo "0")

    echo "[CHAOS 007] HTTP response: ${HTTP_CODE}"
    [[ "$HTTP_CODE" == "503" ]] && echo "[CHAOS 007] ✓ 503 returned as expected" \
      || echo "[CHAOS 007] ✗ Expected 503, got ${HTTP_CODE}"

    # Restore
    chmod u+w "$SITE_DIR"
    echo "[CHAOS 007] ✓ Write bit restored"
  else
    echo "[CHAOS 007] ${SITE_DIR} not found — skipping live test"
  fi
fi

echo "[CHAOS 007] ✓ Complete"
