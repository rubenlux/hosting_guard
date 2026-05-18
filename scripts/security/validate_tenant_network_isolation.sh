#!/usr/bin/env bash
# validate_tenant_network_isolation.sh
#
# Probes DNS resolution and TCP connectivity from inside a tenant container
# toward every platform-internal service.
#
# Expected secure result: ALL probes should FAIL.
# A PASS on any probe means a tenant can reach a platform service — CRITICAL.
#
# Usage:
#   ./scripts/security/validate_tenant_network_isolation.sh [CONTAINER_NAME]
#
# If CONTAINER_NAME is omitted, a temporary alpine container on
# deploy_tenant_edge_network is used and removed afterward.

set -euo pipefail

TENANT_CONTAINER="${1:-}"
TENANT_NETWORK="${TENANT_NETWORK:-deploy_tenant_edge_network}"
TEMP_CONTAINER=""

# ── colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RESET='\033[0m'
pass() { echo -e "${GREEN}[PASS]${RESET} $*"; }
fail() { echo -e "${RED}[FAIL — CRITICAL]${RESET} $*"; FAILURES=$((FAILURES+1)); }
info() { echo -e "${YELLOW}[INFO]${RESET} $*"; }

FAILURES=0

# ── choose probe container ────────────────────────────────────────────────────
if [[ -z "$TENANT_CONTAINER" ]]; then
  TEMP_CONTAINER="hg-isolation-probe-$$"
  info "Launching temporary probe container on $TENANT_NETWORK..."
  docker run -d --name "$TEMP_CONTAINER" \
    --network "$TENANT_NETWORK" \
    --rm \
    alpine:3.19 sleep 120 >/dev/null
  TENANT_CONTAINER="$TEMP_CONTAINER"
  info "Probe container: $TENANT_CONTAINER"
fi

cleanup() {
  if [[ -n "$TEMP_CONTAINER" ]]; then
    docker rm -f "$TEMP_CONTAINER" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

# Install tools inside the alpine probe (no-op if already present)
docker exec "$TENANT_CONTAINER" sh -c "apk add --no-cache bind-tools netcat-openbsd curl >/dev/null 2>&1" || true

echo ""
echo "══════════════════════════════════════════════════════════════════"
echo "  Tenant Network Isolation Validation"
echo "  Probe: $TENANT_CONTAINER  |  Network: $TENANT_NETWORK"
echo "══════════════════════════════════════════════════════════════════"
echo ""

# ── probe function ────────────────────────────────────────────────────────────
# probe HOST PORT SERVICE_LABEL
probe() {
  local host="$1" port="$2" label="$3"
  local resolved ip=""

  echo "--- $label ($host:$port) ---"

  # 1. DNS resolution
  resolved=$(docker exec "$TENANT_CONTAINER" getent hosts "$host" 2>/dev/null || true)
  if [[ -n "$resolved" ]]; then
    ip=$(echo "$resolved" | awk '{print $1}')
    fail "DNS resolved: $host → $ip"
  else
    pass "DNS blocked: $host does not resolve"
  fi

  # 2. TCP connect (only attempt if DNS resolved)
  if [[ -n "$ip" ]]; then
    local nc_result
    nc_result=$(docker exec "$TENANT_CONTAINER" \
      sh -c "nc -zw2 $host $port 2>&1 && echo OPEN || echo CLOSED")
    if echo "$nc_result" | grep -q "OPEN"; then
      fail "TCP connect succeeded: $host:$port is reachable"
    else
      pass "TCP blocked: $host:$port refused/timeout"
    fi

    # 3. HTTP probe (opportunistic — only for http services)
    if [[ "$port" == "8000" || "$port" == "9090" || "$port" == "9093" ]]; then
      local http_code
      http_code=$(docker exec "$TENANT_CONTAINER" \
        sh -c "curl -s -o /dev/null -w '%{http_code}' --connect-timeout 2 http://$host:$port/ 2>/dev/null || echo 000")
      if [[ "$http_code" != "000" ]]; then
        fail "HTTP reachable: $host:$port returned HTTP $http_code"
      else
        pass "HTTP blocked: $host:$port not reachable"
      fi
    fi
  fi

  echo ""
}

# ── platform services to probe ────────────────────────────────────────────────
probe redis              6379  "Redis (token store)"
probe hosting_guard      8000  "App API (FastAPI)"
probe prometheus         9090  "Prometheus"
probe alertmanager       9093  "Alertmanager"
probe hg_scheduler       8000  "Scheduler"
probe hg_worker          8000  "Worker"
probe docker_socket_proxy 2375 "Docker Socket Proxy"
probe pgbouncer          5432  "PgBouncer"
probe hosting_guard_db   5432  "PostgreSQL"

# ── summary ───────────────────────────────────────────────────────────────────
echo "══════════════════════════════════════════════════════════════════"
if [[ "$FAILURES" -eq 0 ]]; then
  echo -e "${GREEN}  ALL PROBES PASSED — tenant network is isolated${RESET}"
  echo "══════════════════════════════════════════════════════════════════"
  exit 0
else
  echo -e "${RED}  $FAILURES CRITICAL FAILURE(S) — tenants can reach platform services${RESET}"
  echo "  Review the FAIL lines above and harden network segmentation."
  echo "══════════════════════════════════════════════════════════════════"
  exit 1
fi
