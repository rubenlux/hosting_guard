#!/usr/bin/env bash
# Chaos 003 — Remove forwardauth middleware YAML, validate detection + auto-repair
# Validates: FORWARDAUTH_MIDDLEWARE_DOCKER_MISSING → auto_repair_allowed=true → regenerate
set -euo pipefail

MIDDLEWARE_FILE="/opt/traefik-dynamic/tenant-forwardauth-middleware.yml"
BACKUP="${MIDDLEWARE_FILE}.chaos_backup_$(date +%s)"

echo "[CHAOS 003] Remove forwardauth middleware YAML"

# ── Signature detection test (no live change needed) ─────────────────────────
python3 - << 'PYEOF'
import sys
sys.path.insert(0, '.')
from app.services.incidents.incident_knowledge_service import match_error_signature

text = "middleware hg-forwardauth@docker does not exist"
matches = match_error_signature(text)

if not matches:
    print("[CHAOS 003] ✗ Signature not matched")
    sys.exit(1)

best = matches[0]
expected = "FORWARDAUTH_MIDDLEWARE_DOCKER_MISSING"
print(f"[CHAOS 003] Matched: {best.incident_id} (confidence={best.confidence})")

if best.incident_id == expected:
    print(f"[CHAOS 003] ✓ Correct runbook: {expected}")
else:
    print(f"[CHAOS 003] ✗ Expected {expected}, got {best.incident_id}")
    sys.exit(1)

if best.auto_repair_allowed:
    print("[CHAOS 003] ✓ auto_repair_allowed=True (can regenerate middleware file)")
else:
    print("[CHAOS 003] ✗ Expected auto_repair_allowed=True")
    sys.exit(1)

if "regenerate_file_provider_forwardauth" in best.safe_actions:
    print("[CHAOS 003] ✓ safe action 'regenerate_file_provider_forwardauth' present")
else:
    print("[CHAOS 003] ✗ Missing expected safe action")
    sys.exit(1)

if "disable_forwardauth_middleware" in best.forbidden_actions:
    print("[CHAOS 003] ✓ 'disable_forwardauth_middleware' correctly forbidden")
else:
    print("[CHAOS 003] ✗ Expected 'disable_forwardauth_middleware' in forbidden_actions")
    sys.exit(1)

PYEOF

# ── Live test (if middleware file exists) ─────────────────────────────────────
if [[ -f "$MIDDLEWARE_FILE" ]]; then
  echo "[CHAOS 003] Running live file deletion test..."
  cp "$MIDDLEWARE_FILE" "$BACKUP"
  rm "$MIDDLEWARE_FILE"
  echo "[CHAOS 003] Middleware file deleted"
  sleep 2

  # Platform repair endpoint should detect and recreate it
  if [[ -n "${ADMIN_TOKEN:-}" ]]; then
    curl -s -X POST "http://localhost:8000/admin/router-health/platform/repair" \
      -b "access_token=${ADMIN_TOKEN}" \
      -H "Content-Type: application/json" \
      -d '{"dry_run": false}' | python3 -c "import sys,json; d=json.load(sys.stdin); print('[CHAOS 003] Repair result:', d)"
  fi

  # Restore
  cp "$BACKUP" "$MIDDLEWARE_FILE"
  rm "$BACKUP"
  echo "[CHAOS 003] ✓ Middleware file restored"
else
  echo "[CHAOS 003] Middleware file not present on this host — skipping live test"
fi

echo "[CHAOS 003] ✓ Complete"
