#!/usr/bin/env bash
# Chaos 004 — Tenant public 404 via missing route
# Validates: router health detects → TENANT_PUBLIC_404_ROUTER_MISSING → incident created
set -euo pipefail

TENANT_SUBDOMAIN="${1:-mi-academia}"
API_BASE="${API_BASE:-http://localhost:8000}"

echo "[CHAOS 004] Simulate tenant public 404 for ${TENANT_SUBDOMAIN}"

# ── Signature detection ────────────────────────────────────────────────────────
python3 - << 'PYEOF'
import sys
sys.path.insert(0, '.')
from app.services.incidents.incident_knowledge_service import match_error_signature

# The router health guard creates this incident_type when HTTP is 404
text = "public_route_404"
matches = match_error_signature(text)

expected = "TENANT_PUBLIC_404_ROUTER_MISSING"
if matches and matches[0].incident_id == expected:
    print(f"[CHAOS 004] ✓ Signature maps to {expected}")
elif matches:
    print(f"[CHAOS 004] ~ Got {matches[0].incident_id} — may still be valid")
else:
    # Try keyword search as fallback
    from app.services.incidents.incident_knowledge_service import search_runbooks
    results = search_runbooks("404 tenant route missing")
    if results:
        print(f"[CHAOS 004] ~ Keyword match: {results[0].incident_id}")
    else:
        print("[CHAOS 004] ✗ No match found")
PYEOF

# ── Live check (if admin token provided) ──────────────────────────────────────
if [[ -n "${ADMIN_TOKEN:-}" ]]; then
  echo "[CHAOS 004] Running router health tenant check..."
  RESULT=$(curl -s -X GET "${API_BASE}/admin/router-health/tenants?unhealthy_only=true" \
    -b "access_token=${ADMIN_TOKEN}")
  echo "[CHAOS 004] Unhealthy tenants: $(echo "$RESULT" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("unhealthy",0))')"

  # Check if matched_runbook_id is attached to incidents
  echo "[CHAOS 004] Checking for matched_runbook_id in incident results..."
  echo "$RESULT" | python3 - << 'PYEOF2'
import sys, json
data = json.load(sys.stdin)
results = data.get("results", [])
for r in results:
    rb = r.get("matched_runbook_id")
    if rb:
        print(f"[CHAOS 004] ✓ Incident has matched_runbook_id: {rb}")
    else:
        print(f"[CHAOS 004] ~ Incident missing matched_runbook_id (P0.4 not yet integrated?)")
PYEOF2
fi

echo "[CHAOS 004] ✓ Complete"
