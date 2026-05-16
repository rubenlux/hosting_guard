#!/usr/bin/env bash
# =============================================================================
# validate_provisioning_gate_live.sh
# =============================================================================
# Runs ProvisioningGate checks against live tenant(s).
# Reads directly from the database and Docker; no API token required.
#
# Usage:
#   ./validate_provisioning_gate_live.sh                  # all active tenants
#   ./validate_provisioning_gate_live.sh 42               # single hosting_id
#   ./validate_provisioning_gate_live.sh 42 --check-http  # with HTTP check
#
# Environment (read from /opt/deploy/.env if present):
#   DATABASE_URL  — PostgreSQL DSN (postgresql://user:pass@host:5432/db)
#   TRAEFIK_DYNAMIC_DIR — defaults to /opt/traefik-dynamic
#   CLIENTS_DIR         — defaults to /opt/clients
# =============================================================================

set -euo pipefail

# ── Config ───────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="/opt/deploy/.env"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  set -a; source "${ENV_FILE}"; set +a
fi

TRAEFIK_DYNAMIC_DIR="${TRAEFIK_DYNAMIC_DIR:-/opt/traefik-dynamic}"
CLIENTS_DIR="${CLIENTS_DIR:-/opt/clients}"
CHECK_HTTP=false
TARGET_HOSTING_ID=""

# ── Argument parsing ─────────────────────────────────────────────────────────
for arg in "$@"; do
  case "${arg}" in
    --check-http) CHECK_HTTP=true ;;
    --help|-h)
      echo "Usage: $0 [hosting_id] [--check-http]"
      exit 0
      ;;
    [0-9]*) TARGET_HOSTING_ID="${arg}" ;;
  esac
done

# ── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
YEL='\033[1;33m'
GRN='\033[0;32m'
CYN='\033[0;36m'
RST='\033[0m'

ok()   { echo -e "${GRN}  ✓${RST} $*"; }
warn() { echo -e "${YEL}  ⚠${RST} $*"; }
fail() { echo -e "${RED}  ✗${RST} $*"; }
info() { echo -e "${CYN}  →${RST} $*"; }

# ── Python runner ─────────────────────────────────────────────────────────────
# Run the ProvisioningGate via the project's venv Python.
PYTHON="${REPO_ROOT}/.venv/Scripts/python"
if [[ ! -f "${PYTHON}" ]]; then
  PYTHON="${REPO_ROOT}/.venv/bin/python"
fi
if [[ ! -f "${PYTHON}" ]]; then
  PYTHON="python3"
fi

run_gate() {
  local hosting_id="$1"
  local container_name="$2"
  local subdomain="$3"

  local check_http_flag="False"
  if [[ "${CHECK_HTTP}" == "true" ]]; then
    check_http_flag="True"
  fi

  "${PYTHON}" - <<PYEOF
import sys, json
sys.path.insert(0, '${REPO_ROOT}')

import app.services.provisioning_gate as _g

# Override paths to match host (script runs on the host, not inside container)
_g._TRAEFIK_DYNAMIC_DIR = '${TRAEFIK_DYNAMIC_DIR}'
_g._CLIENTS_DIR         = '${CLIENTS_DIR}'

result = _g.validate_static_tenant_provisioning(
    hosting_id=${hosting_id},
    container_name='${container_name}',
    subdomain='${subdomain}',
    check_http=${check_http_flag},
    http_timeout=8.0,
)
print(json.dumps(result.to_dict(), indent=2))
PYEOF
}

# ── Database query ────────────────────────────────────────────────────────────
query_tenants() {
  local filter=""
  if [[ -n "${TARGET_HOSTING_ID}" ]]; then
    filter="AND hosting_id = ${TARGET_HOSTING_ID}"
  fi

  psql "${DATABASE_URL}" -t -A -F$'\t' <<SQL
SELECT hosting_id, container_name, subdomain
FROM hostings
WHERE status IN ('active', 'active_with_placeholder', 'pending_content',
                 'routing_degraded', 'routing_failed', 'provisioning_failed')
  AND container_name IS NOT NULL AND container_name <> ''
  AND subdomain IS NOT NULL AND subdomain <> ''
  ${filter}
ORDER BY hosting_id;
SQL
}

# ── Main ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYN}HostingGuard — Provisioning Gate Live Validator${RST}"
echo -e "${CYN}TRAEFIK_DYNAMIC_DIR: ${TRAEFIK_DYNAMIC_DIR}${RST}"
echo -e "${CYN}CLIENTS_DIR:         ${CLIENTS_DIR}${RST}"
echo -e "${CYN}check_http:          ${CHECK_HTTP}${RST}"
if [[ "${CHECK_HTTP}" == "false" ]]; then
  echo -e "${YEL}  ⚠ check_http=false — TLS/Cloudflare errors (526, SSL cert) will NOT be detected.${RST}"
  echo -e "${YEL}    Use --check-http to validate public HTTPS reachability.${RST}"
fi
echo ""

PASS=0
FAIL=0
WARN=0

while IFS=$'\t' read -r hosting_id container_name subdomain; do
  [[ -z "${hosting_id}" ]] && continue

  echo -e "─────────────────────────────────────────────────"
  info "hosting_id=${hosting_id}  container=${container_name}  subdomain=${subdomain}"

  result_json="$(run_gate "${hosting_id}" "${container_name}" "${subdomain}" 2>&1)" || {
    fail "Gate runner failed for hosting_id=${hosting_id}: ${result_json}"
    (( FAIL++ )) || true
    continue
  }

  status="$(echo "${result_json}" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["status"])')"
  ok_flag="$(echo "${result_json}" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["ok"])')"
  reason="$(echo "${result_json}" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["reason"])')"

  # Annotate result with check scope so STRUCTURAL PASS vs RUNTIME PASS is clear
  scope_label="STRUCTURAL"
  if [[ "${CHECK_HTTP}" == "true" ]]; then
    scope_label="FULL"
  fi

  yaml_valid="$(echo "${result_json}" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("checks",{}).get("yaml_structure_valid","?"))')"
  if [[ "${yaml_valid}" == "False" ]]; then
    fail "YAML INVALID — Traefik will reject this file (middlewares nested under tls)"
    (( FAIL++ )) || true
    continue
  fi

  case "${status}" in
    active)
      ok "[${scope_label} PASS] status=active — ${reason}"
      (( PASS++ )) || true
      ;;
    active_with_placeholder)
      if [[ "${CHECK_HTTP}" == "false" ]]; then
        warn "[STRUCTURAL PASS — runtime not validated] status=active_with_placeholder — ${reason}"
        warn "    Run with --check-http to confirm public route + TLS are healthy."
      else
        ok "[${scope_label} PASS] status=active_with_placeholder — ${reason}"
      fi
      (( PASS++ )) || true
      ;;
    pending_content)
      warn "[${scope_label}] status=pending_content — ${reason}"
      (( WARN++ )) || true
      ;;
    routing_degraded)
      warn "[${scope_label}] status=routing_degraded — ${reason}"
      echo "${result_json}" | python3 -c '
import sys, json
d = json.load(sys.stdin)
for a in d.get("safe_actions", []):
    print(f"       safe_action: {a}")
for a in d.get("forbidden_actions", []):
    print(f"    forbidden: {a}")
'
      (( WARN++ )) || true
      ;;
    routing_failed|provisioning_failed)
      fail "[RUNTIME FAIL] status=${status} — ${reason}"
      echo "${result_json}" | python3 -c '
import sys, json
d = json.load(sys.stdin)
checks = d.get("checks", {})
for k, v in checks.items():
    if v is False or v is None:
        print(f"     FAIL check: {k}={v}")
'
      (( FAIL++ )) || true
      ;;
    *)
      warn "[${scope_label}] status=${status} (unknown) — ${reason}"
      (( WARN++ )) || true
      ;;
  esac

done < <(query_tenants)

echo ""
echo -e "═════════════════════════════════════════════════"
echo -e "${GRN}PASS: ${PASS}${RST}  ${YEL}WARN: ${WARN}${RST}  ${RED}FAIL: ${FAIL}${RST}"
echo ""

if (( FAIL > 0 )); then
  exit 1
fi
exit 0
