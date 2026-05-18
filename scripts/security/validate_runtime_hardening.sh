#!/usr/bin/env bash
# validate_runtime_hardening.sh
#
# Validates runtime security posture of all running tenant containers (user_*).
#
# Checks (per container):
#   FAIL  — container is privileged
#   FAIL  — /var/run/docker.sock is mounted
#   FAIL  — container is on socket_proxy_network
#   WARN  — container is NOT only on tenant_edge_network
#   WARN  — site mount is not read-only
#   WARN  — no pids limit set
#   WARN  — no memory limit set
#   WARN  — no cpu quota set
#
# Recommended file permissions (reference — not validated at runtime):
#   /opt/deploy/.env.production        → root:deploy  640
#   /opt/deploy/docker-compose.yml     → root:deploy  640
#   /root/.env.production.backup*      → root:root    600
#
# Exit codes:
#   0 — all containers passed (no FAIL)
#   1 — one or more containers have FAIL findings
#
# Usage:
#   sudo ./scripts/security/validate_runtime_hardening.sh [--tenant CONTAINER]

set -euo pipefail

TENANT_NETWORK="${TENANT_NETWORK:-deploy_tenant_edge_network}"
SOCKET_PROXY_NETWORK="${SOCKET_PROXY_NETWORK:-deploy_socket_proxy_network}"
FILTER_CONTAINER=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tenant) FILTER_CONTAINER="$2"; shift 2 ;;
    *) echo "Unknown flag: $1"; exit 1 ;;
  esac
done

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RESET='\033[0m'

TOTAL=0; PASS=0; WARN_COUNT=0; FAIL_COUNT=0

pass()  { echo -e "  ${GREEN}[PASS]${RESET}  $*"; PASS=$((PASS+1)); }
fail()  { echo -e "  ${RED}[FAIL]${RESET}  $*"; FAIL_COUNT=$((FAIL_COUNT+1)); }
warn()  { echo -e "  ${YELLOW}[WARN]${RESET}  $*"; WARN_COUNT=$((WARN_COUNT+1)); }
info()  { echo -e "${CYAN}[INFO]${RESET}  $*"; }
header(){ echo ""; echo "┌─ $*"; }

# ── collect containers ────────────────────────────────────────────────────────
if [[ -n "$FILTER_CONTAINER" ]]; then
  mapfile -t CONTAINERS < <(echo "$FILTER_CONTAINER")
else
  mapfile -t CONTAINERS < <(docker ps --filter "name=user_" --format '{{.Names}}' | sort)
fi

if [[ ${#CONTAINERS[@]} -eq 0 ]]; then
  info "No running tenant containers found (pattern: user_*)."
  exit 0
fi

echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "  Runtime Hardening Validation — ${#CONTAINERS[@]} tenant container(s)"
echo "  Tenant network: $TENANT_NETWORK"
echo "════════════════════════════════════════════════════════════════════"

for CONTAINER in "${CONTAINERS[@]}"; do
  TOTAL=$((TOTAL+1))
  header "$CONTAINER"

  # Fetch all relevant inspect fields in one call to avoid N×docker-inspect overhead
  INSPECT=$(docker inspect \
    --format '{{json .HostConfig}}|||{{json .NetworkSettings.Networks}}' \
    "$CONTAINER" 2>/dev/null || echo "|||")

  HOST_CFG=$(echo "$INSPECT" | cut -d'|' -f1)
  NETWORKS_JSON=$(echo "$INSPECT" | cut -d'|' -f4)

  # ── FAIL: privileged ─────────────────────────────────────────────────────
  PRIVILEGED=$(echo "$HOST_CFG" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('Privileged','false'))" 2>/dev/null || echo "false")
  if [[ "$PRIVILEGED" == "True" ]] || [[ "$PRIVILEGED" == "true" ]]; then
    fail "Container is PRIVILEGED — full host access"
  else
    pass "Not privileged"
  fi

  # ── FAIL: docker.sock mount ───────────────────────────────────────────────
  SOCK_MOUNT=$(echo "$HOST_CFG" | python3 -c "
import json, sys
d = json.load(sys.stdin)
binds = d.get('Binds') or []
for b in binds:
    if '/var/run/docker.sock' in b:
        print(b)
        break
" 2>/dev/null || true)
  if [[ -n "$SOCK_MOUNT" ]]; then
    fail "docker.sock mounted: $SOCK_MOUNT"
  else
    pass "No docker.sock mount"
  fi

  # ── FAIL: socket_proxy_network membership ────────────────────────────────
  ON_SOCKET=$(echo "$NETWORKS_JSON" | python3 -c "
import json, sys, os
nets = json.load(sys.stdin)
print('yes' if os.environ.get('SOCKET_PROXY_NETWORK','deploy_socket_proxy_network') in nets else 'no')
" SOCKET_PROXY_NETWORK="$SOCKET_PROXY_NETWORK" 2>/dev/null || echo "no")
  if [[ "$ON_SOCKET" == "yes" ]]; then
    fail "Container is on $SOCKET_PROXY_NETWORK — can reach docker-socket-proxy"
  else
    pass "Not on socket_proxy_network"
  fi

  # ── WARN: only on tenant_edge_network ────────────────────────────────────
  UNEXPECTED_NETS=$(echo "$NETWORKS_JSON" | python3 -c "
import json, sys, os
nets = list(json.load(sys.stdin).keys())
tenant = os.environ.get('TENANT_NETWORK','deploy_tenant_edge_network')
extra = [n for n in nets if n != tenant]
print(' '.join(extra))
" TENANT_NETWORK="$TENANT_NETWORK" 2>/dev/null || true)
  ON_TENANT=$(echo "$NETWORKS_JSON" | python3 -c "
import json, sys, os
nets = list(json.load(sys.stdin).keys())
tenant = os.environ.get('TENANT_NETWORK','deploy_tenant_edge_network')
print('yes' if tenant in nets else 'no')
" TENANT_NETWORK="$TENANT_NETWORK" 2>/dev/null || echo "no")

  if [[ "$ON_TENANT" != "yes" ]]; then
    warn "NOT on $TENANT_NETWORK — $(echo "$NETWORKS_JSON" | python3 -c "import json,sys; print(' '.join(json.load(sys.stdin).keys()))" 2>/dev/null || echo '?')"
  elif [[ -n "$UNEXPECTED_NETS" ]]; then
    warn "Also on non-tenant networks: $UNEXPECTED_NETS"
  else
    pass "Only on $TENANT_NETWORK"
  fi

  # ── WARN: pids limit ─────────────────────────────────────────────────────
  # dict.get('PidsLimit', 0) returns Python None (not 0) when JSON has null.
  # Normalize: None/null/0/negative → 0 so the bash comparison is always numeric.
  PIDS=$(echo "$HOST_CFG" | python3 -c "
import json,sys
d=json.load(sys.stdin)
v=d.get('PidsLimit')
print(0 if not v or v <= 0 else int(v))
" 2>/dev/null || echo "0")
  if [[ "$PIDS" -le 0 ]]; then
    warn "No pids limit — fork-bomb possible (add --pids-limit)"
  else
    pass "pids limit: $PIDS"
  fi

  # ── WARN: memory limit ───────────────────────────────────────────────────
  MEM=$(echo "$HOST_CFG" | python3 -c "
import json,sys
d=json.load(sys.stdin)
v=d.get('Memory')
print(0 if not v or v <= 0 else int(v))
" 2>/dev/null || echo "0")
  if [[ "$MEM" -le 0 ]]; then
    warn "No memory limit (add --memory)"
  else
    MEM_MB=$(( MEM / 1024 / 1024 ))
    pass "Memory limit: ${MEM_MB}MB"
  fi

  # ── WARN: cpu quota ──────────────────────────────────────────────────────
  CPU=$(echo "$HOST_CFG" | python3 -c "
import json,sys
d=json.load(sys.stdin)
v=d.get('NanoCpus')
print(0 if not v or v <= 0 else int(v))
" 2>/dev/null || echo "0")
  if [[ "$CPU" -le 0 ]]; then
    warn "No CPU limit (add --cpus)"
  else
    CPU_CORES=$(echo "$CPU" | python3 -c "import sys; v=int(sys.stdin.read().strip()); print(f'{v/1e9:.2f}')" 2>/dev/null || echo "?")
    pass "CPU limit: ${CPU_CORES} cores"
  fi

  # ── WARN: site mount read-only ───────────────────────────────────────────
  RO_CHECK=$(echo "$HOST_CFG" | python3 -c "
import json, sys
d = json.load(sys.stdin)
mounts = d.get('Binds') or []
nginx_mounts = [b for b in mounts if '/usr/share/nginx/html' in b]
if not nginx_mounts:
    print('no_nginx_mount')
elif any(':ro' in b for b in nginx_mounts):
    print('ro')
else:
    print('rw:' + '|'.join(nginx_mounts))
" 2>/dev/null || echo "unknown")
  case "$RO_CHECK" in
    ro)            pass "Site mount is read-only (:ro)" ;;
    no_nginx_mount) pass "No nginx site mount (non-static container)" ;;
    rw:*)          warn "Site mount is NOT read-only: ${RO_CHECK#rw:}" ;;
    *)             warn "Could not determine site mount mode" ;;
  esac

  # ── WARN: no-new-privileges ──────────────────────────────────────────────
  NNP=$(echo "$HOST_CFG" | python3 -c "
import json, sys
d = json.load(sys.stdin)
opts = d.get('SecurityOpt') or []
print('yes' if any('no-new-privileges' in o for o in opts) else 'no')
" 2>/dev/null || echo "no")
  if [[ "$NNP" == "yes" ]]; then
    pass "no-new-privileges set"
  else
    warn "no-new-privileges not set (add --security-opt no-new-privileges:true)"
  fi

  echo "└───"
done

# ── summary ───────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "  Results: $PASS passed, $WARN_COUNT warnings, $FAIL_COUNT failures"
echo "  Containers checked: $TOTAL"
echo "════════════════════════════════════════════════════════════════════"

if [[ $FAIL_COUNT -gt 0 ]]; then
  echo -e "${RED}  CRITICAL — $FAIL_COUNT container(s) have security violations${RESET}"
  echo ""
  echo "  Common fixes:"
  echo "    Privileged:     docker inspect --format '{{.HostConfig.Privileged}}' <container>"
  echo "    Docker socket:  docker inspect --format '{{.HostConfig.Binds}}' <container>"
  echo "    Network:        sudo ./scripts/ops/migrate_tenants_to_tenant_edge_network.sh"
  echo ""
  exit 1
elif [[ $WARN_COUNT -gt 0 ]]; then
  echo -e "${YELLOW}  WARNINGS — $WARN_COUNT item(s) need attention (existing containers need recreation)${RESET}"
  echo ""
  echo "  New tenants created after P4C will have these settings applied automatically."
  echo "  Existing containers: recreate via the platform (delete + redeploy) to apply limits."
  echo ""
  exit 0
else
  echo -e "${GREEN}  SECURE — all tenant containers passed runtime hardening checks${RESET}"
  echo ""
  exit 0
fi
