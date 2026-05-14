#!/usr/bin/env bash
# Chaos 011 — WordPress xmlrpc.php exposed
# Validates: WP_XMLRPC_EXPOSED_APACHE_RUNTIME → block_xmlrpc_apache safe action
set -euo pipefail

TENANT_DOMAIN="${1:-}"

echo "[CHAOS 011] Validate xmlrpc.php exposure detection"

# ── Signature matching ─────────────────────────────────────────────────────────
python3 - << 'PYEOF'
import sys
sys.path.insert(0, '.')
from app.services.incidents.incident_knowledge_service import match_error_signature

texts = [
    "XML-RPC server accepts POST requests only",
    "xmlrpc.php",
]
expected = "WP_XMLRPC_EXPOSED_APACHE_RUNTIME"

for text in texts:
    matches = match_error_signature(text)
    if matches and matches[0].incident_id == expected:
        print(f"[CHAOS 011] ✓ '{text}' → {expected}")
        print(f"[CHAOS 011] auto_repair_allowed: {matches[0].auto_repair_allowed}")
    elif matches:
        print(f"[CHAOS 011] ~ '{text}' → {matches[0].incident_id}")
    else:
        print(f"[CHAOS 011] ✗ no match for: {text}")

from app.services.incidents.incident_knowledge_service import get_safe_actions, get_forbidden_actions
safe = get_safe_actions(expected)
forbidden = get_forbidden_actions(expected)
if "block_xmlrpc_apache" in safe:
    print("[CHAOS 011] ✓ block_xmlrpc_apache in safe_actions")
if "delete_xmlrpc_file_from_container" in forbidden:
    print("[CHAOS 011] ✓ delete_xmlrpc_file_from_container correctly forbidden")
if "auto_restart_wp_container" in forbidden:
    print("[CHAOS 011] ✓ auto_restart_wp_container correctly forbidden")
PYEOF

# ── Live check: xmlrpc.php accessible? ────────────────────────────────────────
if [[ -n "$TENANT_DOMAIN" ]]; then
  HTTP_CODE=$(curl -s -o /tmp/chaos011_body.txt -w "%{http_code}" \
    "https://${TENANT_DOMAIN}/xmlrpc.php" --max-time 5 || echo "0")
  echo "[CHAOS 011] GET /xmlrpc.php → HTTP ${HTTP_CODE}"

  if [[ "$HTTP_CODE" == "403" ]]; then
    echo "[CHAOS 011] ✓ xmlrpc.php blocked (403) — secure"
  elif [[ "$HTTP_CODE" == "200" ]]; then
    BODY=$(cat /tmp/chaos011_body.txt)
    if echo "$BODY" | grep -q "XML-RPC"; then
      echo "[CHAOS 011] ✗ xmlrpc.php EXPOSED — incident should be raised"
    fi
  else
    echo "[CHAOS 011] ~ HTTP ${HTTP_CODE} — may not be WordPress"
  fi
  rm -f /tmp/chaos011_body.txt
fi

echo "[CHAOS 011] ✓ Complete"
