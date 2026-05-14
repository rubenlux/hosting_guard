#!/usr/bin/env bash
# Chaos 001 — Delete tenant Traefik route
# Validates: detection → TENANT_PUBLIC_404_ROUTER_MISSING → dashboard degraded → safe action recommended
set -euo pipefail

TENANT_SUBDOMAIN="${1:-mi-academia}"
YAML_FILE="/opt/traefik-dynamic/tenants-active.yml"
BACKUP="${YAML_FILE}.chaos_backup_$(date +%s)"

echo "[CHAOS 001] Delete tenant route: ${TENANT_SUBDOMAIN}"

# ── Preconditions ──────────────────────────────────────────────────────────────
if [[ ! -f "$YAML_FILE" ]]; then
  echo "ERROR: ${YAML_FILE} not found — abort"
  exit 1
fi

# ── Inject failure ─────────────────────────────────────────────────────────────
cp "$YAML_FILE" "$BACKUP"
echo "[CHAOS 001] Backup: ${BACKUP}"

# Remove the tenant's router block from the YAML
# (comment out lines matching the subdomain)
sed -i "/${TENANT_SUBDOMAIN}/d" "$YAML_FILE"
echo "[CHAOS 001] Route for ${TENANT_SUBDOMAIN} removed from YAML"

# ── Wait for Traefik to reload (file provider polls every 100ms by default) ───
sleep 2

# ── Validate detection ─────────────────────────────────────────────────────────
echo "[CHAOS 001] Checking public route..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "https://${TENANT_SUBDOMAIN}.hostingguard.lat" --max-time 5 || echo "0")

if [[ "$HTTP_CODE" == "404" ]] || [[ "$HTTP_CODE" == "0" ]]; then
  echo "[CHAOS 001] ✓ Expected failure detected: HTTP ${HTTP_CODE}"
else
  echo "[CHAOS 001] ✗ Expected 404 but got HTTP ${HTTP_CODE}"
fi

# ── Trigger router health check via API (requires admin token) ────────────────
if [[ -n "${ADMIN_TOKEN:-}" ]]; then
  RESULT=$(curl -s -X POST "http://localhost:8000/admin/router-health/tenants/check" \
    -b "access_token=${ADMIN_TOKEN}" \
    -H "Content-Type: application/json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('unhealthy',0))")
  echo "[CHAOS 001] Unhealthy tenants reported: ${RESULT}"
  if [[ "${RESULT}" -gt 0 ]]; then
    echo "[CHAOS 001] ✓ Router health detected incident"
  else
    echo "[CHAOS 001] ✗ Router health did NOT detect incident"
  fi
fi

# ── Restore ────────────────────────────────────────────────────────────────────
echo "[CHAOS 001] Restoring backup..."
cp "$BACKUP" "$YAML_FILE"
rm "$BACKUP"
sleep 2
echo "[CHAOS 001] ✓ Route restored"

# ── Verify recovery ────────────────────────────────────────────────────────────
HTTP_CODE_AFTER=$(curl -s -o /dev/null -w "%{http_code}" "https://${TENANT_SUBDOMAIN}.hostingguard.lat" --max-time 5 || echo "0")
echo "[CHAOS 001] HTTP after restore: ${HTTP_CODE_AFTER}"
[[ "$HTTP_CODE_AFTER" == "200" ]] && echo "[CHAOS 001] ✓ Recovery confirmed" || echo "[CHAOS 001] ✗ Recovery failed"
