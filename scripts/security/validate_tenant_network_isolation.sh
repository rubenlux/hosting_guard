#!/usr/bin/env bash
# validate_tenant_network_isolation.sh
#
# Validates that a tenant container cannot reach platform-internal services.
#
# Expected: ALL platform probes FAIL.
# Any PASS = tenant can reach internal infrastructure = CRITICAL.
#
# Usage:
#   sudo ./scripts/security/validate_tenant_network_isolation.sh CONTAINER_NAME [--domain DOMAIN]
#   sudo ./scripts/security/validate_tenant_network_isolation.sh               (spawns temp container)
#
# Options:
#   --domain DOMAIN   Also verify https://DOMAIN returns 2xx from the internet.
#
# Examples:
#   sudo ./validate_tenant_network_isolation.sh user_1_mi-academia_a3dab0
#   sudo ./validate_tenant_network_isolation.sh user_1_mi-academia_a3dab0 --domain mi-academia.hostingguard.lat
#   sudo ./validate_tenant_network_isolation.sh --domain mi-academia.hostingguard.lat

set -euo pipefail

TENANT_CONTAINER=""
DOMAIN=""
TENANT_NETWORK="${TENANT_NETWORK:-deploy_tenant_edge_network}"
TEMP_CONTAINER=""

# ── parse args ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN="$2"; shift 2 ;;
    --*)      echo "Unknown flag: $1"; exit 1 ;;
    *)        TENANT_CONTAINER="$1"; shift ;;
  esac
done

# ── colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RESET='\033[0m'
PASS=0; FAILURES=0
pass()  { echo -e "  ${GREEN}[PASS]${RESET} $*";  PASS=$((PASS+1)); }
fail()  { echo -e "  ${RED}[FAIL]${RESET} $*";  FAILURES=$((FAILURES+1)); }
info()  { echo -e "${CYAN}[INFO]${RESET} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${RESET} $*"; }
section(){ echo ""; echo -e "${YELLOW}── $* ──${RESET}"; }

# ── ensure probe container ────────────────────────────────────────────────────
if [[ -z "$TENANT_CONTAINER" ]]; then
  TEMP_CONTAINER="hg-isolation-probe-$$"
  info "No container specified — launching temp probe on $TENANT_NETWORK"
  docker run -d --name "$TEMP_CONTAINER" --network "$TENANT_NETWORK" \
    alpine:3.19 sleep 120 >/dev/null 2>&1
  TENANT_CONTAINER="$TEMP_CONTAINER"
  info "Probe: $TENANT_CONTAINER"
fi

cleanup() {
  [[ -n "$TEMP_CONTAINER" ]] && docker rm -f "$TEMP_CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# ── verify container is on tenant_edge_network only ──────────────────────────
section "Container network membership"
CONTAINER_NETS=$(docker inspect --format \
  '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' \
  "$TENANT_CONTAINER" 2>/dev/null | tr ' ' '\n' | grep -v '^$' | sort)

if echo "$CONTAINER_NETS" | grep -qx "$TENANT_NETWORK"; then
  pass "Container is on $TENANT_NETWORK"
else
  fail "Container is NOT on $TENANT_NETWORK (networks: $(echo $CONTAINER_NETS | tr '\n' ' '))"
fi

UNEXPECTED=$(echo "$CONTAINER_NETS" | grep -v "^$TENANT_NETWORK$" || true)
if [[ -n "$UNEXPECTED" ]]; then
  for net in $UNEXPECTED; do
    fail "Container is ALSO on $net — isolation breach if this network reaches platform services"
  done
else
  pass "Container is on tenant_edge_network ONLY"
fi

# ── install probe tools inside container ─────────────────────────────────────
docker exec "$TENANT_CONTAINER" sh -c \
  "apk add --no-cache bind-tools netcat-openbsd curl >/dev/null 2>&1" 2>/dev/null || true

echo ""
echo "══════════════════════════════════════════════════════════════════════"
echo "  Platform Service Isolation Probes"
echo "  Container: $TENANT_CONTAINER"
echo "══════════════════════════════════════════════════════════════════════"

# ── probe: DNS + TCP + HTTP ───────────────────────────────────────────────────
# probe HOST PORT [http|tcp]
probe() {
  local host="$1" port="$2" proto="${3:-tcp}" label="$4"
  local resolved="" ip=""

  section "$label  ($host:$port)"

  # DNS
  resolved=$(docker exec "$TENANT_CONTAINER" getent hosts "$host" 2>/dev/null || true)
  if [[ -n "$resolved" ]]; then
    ip=$(echo "$resolved" | awk '{print $1}' | head -1)
    fail "DNS resolved: $host → $ip"
  else
    pass "DNS blocked: $host does not resolve"
    # Attempt connection by hostname anyway (in case /etc/hosts or ndots tricks)
    ip="$host"
  fi

  # TCP
  local nc_out
  nc_out=$(docker exec "$TENANT_CONTAINER" \
    sh -c "nc -zw2 $ip $port >/dev/null 2>&1 && echo OPEN || echo CLOSED" 2>/dev/null || echo "CLOSED")
  if [[ "$nc_out" == "OPEN" ]]; then
    fail "TCP open: $host:$port is reachable"
  else
    pass "TCP blocked: $host:$port"
  fi

  # HTTP (for http-speaking services)
  if [[ "$proto" == "http" ]]; then
    local raw http_code curl_exit
    # curl -w '%{http_code}' always prints a value — '000' when there is no HTTP
    # response (DNS fail, connection refused, timeout).  The old '|| echo 000'
    # inside the sh -c caused double-printing: curl already wrote '000', then the
    # shell appended another '000', giving '000000'.
    #
    # Fixed: use '; printf :%d $?' to append the curl exit code on the same line,
    # then decide FAIL only when BOTH http_code != 000 AND exit == 0.
    # That way 403/404 (service IS reachable internally) → FAIL, while
    # DNS-fail/timeout/refused (exit != 0) → PASS even with code 000.
    raw=$(docker exec "$TENANT_CONTAINER" \
      sh -c "curl -s -o /dev/null -w '%{http_code}' --connect-timeout 2 http://${ip}:${port}/ 2>/dev/null; printf ':%d' \$?" \
      2>/dev/null || echo "000:1")
    http_code="${raw%%:*}"   # everything before the first colon
    curl_exit="${raw##*:}"   # everything after the last colon
    if [[ "$http_code" != "000" ]] && [[ "$curl_exit" == "0" ]]; then
      fail "HTTP reachable: $host:$port returned $http_code"
    else
      pass "HTTP blocked: $host:$port returned $http_code (curl exit=$curl_exit)"
    fi
  fi
}

probe redis               6379 tcp  "Redis (token store)"
probe hosting_guard       8000 http "App API (FastAPI)"
probe prometheus          9090 http "Prometheus"
probe alertmanager        9093 http "Alertmanager"
probe hg_scheduler        8000 http "Scheduler"
probe hg_worker           8000 http "Worker"
probe docker_socket_proxy 2375 tcp  "Docker Socket Proxy"
probe pgbouncer           5432 tcp  "PgBouncer"
probe hosting_guard_db    5432 tcp  "PostgreSQL"

# ── public domain check ───────────────────────────────────────────────────────
if [[ -n "$DOMAIN" ]]; then
  section "Public domain: $DOMAIN"
  HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' \
    --connect-timeout 8 --max-time 15 \
    "https://$DOMAIN/" 2>/dev/null || echo "000")
  if [[ "$HTTP_CODE" =~ ^2 ]] || [[ "$HTTP_CODE" =~ ^3 ]]; then
    pass "https://$DOMAIN → HTTP $HTTP_CODE (reachable via Traefik)"
  else
    fail "https://$DOMAIN → HTTP $HTTP_CODE (expected 2xx/3xx)"
  fi
fi

# ── summary ───────────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════════════════════"
echo "  Results: $PASS passed, $FAILURES failed"
echo "══════════════════════════════════════════════════════════════════════"
if [[ $FAILURES -eq 0 ]]; then
  echo -e "${GREEN}  SECURE — tenant cannot reach platform services${RESET}"
  exit 0
else
  echo -e "${RED}  CRITICAL — $FAILURES probe(s) succeeded — tenant can reach platform services${RESET}"
  echo "  Apply network isolation: see scripts/ops/migrate_tenants_to_tenant_edge_network.sh"
  exit 1
fi
