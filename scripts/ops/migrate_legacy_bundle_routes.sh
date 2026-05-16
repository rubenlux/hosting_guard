#!/usr/bin/env bash
# =============================================================================
# migrate_legacy_bundle_routes.sh
# =============================================================================
# Generates individual tenant-{id}.yml files for all active tenants that are
# currently only routed via the legacy tenants-active.yml bundle.
#
# Usage:
#   ./migrate_legacy_bundle_routes.sh              # dry-run (prints what would be written)
#   ./migrate_legacy_bundle_routes.sh --apply      # write files to TRAEFIK_DYNAMIC_DIR
#   ./migrate_legacy_bundle_routes.sh 42 --apply   # single hosting_id
#
# Environment (read from /opt/deploy/.env if present):
#   DATABASE_URL        — PostgreSQL DSN
#   TRAEFIK_DYNAMIC_DIR — defaults to /opt/traefik-dynamic
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="/opt/deploy/.env"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  set -a; source "${ENV_FILE}"; set +a
fi

TRAEFIK_DYNAMIC_DIR="${TRAEFIK_DYNAMIC_DIR:-/opt/traefik-dynamic}"
APPLY=false
TARGET_HOSTING_ID=""

for arg in "$@"; do
  case "${arg}" in
    --apply) APPLY=true ;;
    --help|-h)
      echo "Usage: $0 [hosting_id] [--apply]"
      exit 0
      ;;
    [0-9]*) TARGET_HOSTING_ID="${arg}" ;;
  esac
done

RED='\033[0;31m'
YEL='\033[1;33m'
GRN='\033[0;32m'
CYN='\033[0;36m'
RST='\033[0m'

ok()   { echo -e "${GRN}  ✓${RST} $*"; }
warn() { echo -e "${YEL}  ⚠${RST} $*"; }
fail() { echo -e "${RED}  ✗${RST} $*"; }
info() { echo -e "${CYN}  →${RST} $*"; }

PYTHON="${REPO_ROOT}/.venv/Scripts/python"
if [[ ! -f "${PYTHON}" ]]; then
  PYTHON="${REPO_ROOT}/.venv/bin/python"
fi
if [[ ! -f "${PYTHON}" ]]; then
  PYTHON="python3"
fi

BUNDLE_FILE="${TRAEFIK_DYNAMIC_DIR}/tenants-active.yml"

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

generate_yaml() {
  local hosting_id="$1"
  local container_name="$2"
  local subdomain="$3"

  cat <<YAML
# HostingGuard — auto-generated. hosting_id=${hosting_id}
# Migrated from tenants-active.yml bundle by migrate_legacy_bundle_routes.sh
http:
  routers:
    ${container_name}:
      rule: "Host(\`${subdomain}\`)"
      entryPoints:
        - websecure
      tls:
        certResolver: le
      middlewares:
        - hg-forwardauth@file
      service: ${container_name}
      priority: 100
  services:
    ${container_name}:
      loadBalancer:
        servers:
          - url: "http://${container_name}:80"
YAML
}

echo ""
echo -e "${CYN}HostingGuard — Legacy Bundle Route Migration${RST}"
echo -e "${CYN}TRAEFIK_DYNAMIC_DIR: ${TRAEFIK_DYNAMIC_DIR}${RST}"
echo -e "${CYN}Bundle file:         ${BUNDLE_FILE}${RST}"
if [[ "${APPLY}" == "false" ]]; then
  echo -e "${YEL}  DRY-RUN mode — use --apply to write files${RST}"
fi
echo ""

if [[ ! -f "${BUNDLE_FILE}" ]]; then
  warn "Bundle file not found: ${BUNDLE_FILE}"
  warn "Nothing to migrate."
  exit 0
fi

MIGRATED=0
SKIPPED=0
FAIL_COUNT=0

while IFS=$'\t' read -r hosting_id container_name subdomain; do
  [[ -z "${hosting_id}" ]] && continue

  individual_file="${TRAEFIK_DYNAMIC_DIR}/tenant-${hosting_id}.yml"

  if [[ -f "${individual_file}" ]]; then
    info "hosting_id=${hosting_id} — already has individual file, skipping"
    (( SKIPPED++ )) || true
    continue
  fi

  # Only migrate if tenant appears in the bundle
  if ! grep -qF "${container_name}" "${BUNDLE_FILE}" 2>/dev/null; then
    warn "hosting_id=${hosting_id} — not found in bundle (docker_labels only?), skipping"
    (( SKIPPED++ )) || true
    continue
  fi

  echo -e "─────────────────────────────────────────────────"
  info "hosting_id=${hosting_id}  container=${container_name}  subdomain=${subdomain}"

  yaml_content="$(generate_yaml "${hosting_id}" "${container_name}" "${subdomain}")"

  if [[ "${APPLY}" == "true" ]]; then
    tmp_file="${individual_file}.tmp"
    if echo "${yaml_content}" > "${tmp_file}" && mv "${tmp_file}" "${individual_file}"; then
      ok "Written: ${individual_file}"
      (( MIGRATED++ )) || true
    else
      fail "Failed to write: ${individual_file}"
      (( FAIL_COUNT++ )) || true
    fi
  else
    echo -e "${CYN}--- Would write: ${individual_file} ---${RST}"
    echo "${yaml_content}"
    (( MIGRATED++ )) || true
  fi

done < <(query_tenants)

echo ""
echo -e "═════════════════════════════════════════════════"
if [[ "${APPLY}" == "true" ]]; then
  echo -e "${GRN}WRITTEN: ${MIGRATED}${RST}  ${YEL}SKIPPED: ${SKIPPED}${RST}  ${RED}FAILED: ${FAIL_COUNT}${RST}"
  if (( MIGRATED > 0 )); then
    echo ""
    echo -e "${CYN}Next steps:${RST}"
    echo -e "  1. Verify Traefik loaded the new files (no restart needed — hot-reload):"
    echo -e "     curl -s http://traefik:8080/api/http/routers | jq '.[] | select(.name | startswith(\"tenant-\"))'"
    echo -e "  2. Run validate_provisioning_gate_live.sh --check-http to confirm tenants healthy"
    echo -e "  3. Once all tenants have individual files, remove tenants-active.yml"
  fi
else
  echo -e "${YEL}DRY-RUN: ${MIGRATED} file(s) would be written, ${SKIPPED} skipped${RST}"
  echo -e "${YEL}Re-run with --apply to write.${RST}"
fi
echo ""

if (( FAIL_COUNT > 0 )); then
  exit 1
fi
exit 0
