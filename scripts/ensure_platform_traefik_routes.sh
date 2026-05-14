#!/bin/bash
# ensure_platform_traefik_routes.sh
#
# Creates/verifies Traefik dynamic config files for platform routing.
# Idempotent — safe to run on every deploy or ad-hoc.
#
# Manages:
#   /opt/traefik-dynamic/platform-frontend.yml  → hostingguard.lat
#   /opt/traefik-dynamic/platform-api.yml       → api.hostingguard.lat
#
# Does NOT modify:
#   - ForwardAuth middleware (hg-forwardauth — defined in docker-compose app labels)
#   - Tenant routers (custom domains in /opt/traefik-dynamic/*.yml written by domain_checker.py)
#   - docker-compose.yml
#
# Usage:
#   bash scripts/ensure_platform_traefik_routes.sh
#   bash scripts/ensure_platform_traefik_routes.sh --check-only

set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
DYNAMIC_DIR="/opt/traefik-dynamic"
CHECK_ONLY="${1:-}"
PASS=0
FAIL=0

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

log_ok()   { echo -e "  ${GREEN}[OK]${NC}   $*"; PASS=$((PASS+1)); }
log_fail() { echo -e "  ${RED}[FAIL]${NC} $*"; FAIL=$((FAIL+1)); }
log_info() { echo -e "  ${YELLOW}[INFO]${NC} $*"; }
log_head() { echo -e "\n${BOLD}$*${NC}"; }

# ─────────────────────────────────────────────────────────────────────────────
# 1. Ensure dynamic dir exists
# ─────────────────────────────────────────────────────────────────────────────
log_head "=== Platform Traefik Routes ==="

if [ -z "$CHECK_ONLY" ]; then
    mkdir -p "$DYNAMIC_DIR"
    log_info "Dynamic dir: $DYNAMIC_DIR"
fi

# ─────────────────────────────────────────────────────────────────────────────
# 2. platform-frontend.yml
#    Routes: hostingguard.lat + www.hostingguard.lat → frontend:80
#    No ForwardAuth — SPA handles its own auth redirects.
# ─────────────────────────────────────────────────────────────────────────────
FRONTEND_FILE="$DYNAMIC_DIR/platform-frontend.yml"
FRONTEND_CONTENT='# platform-frontend.yml
# Platform router for the main SPA (React/Nginx).
# Managed by scripts/ensure_platform_traefik_routes.sh — do not edit manually.
# Backup before editing: cp platform-frontend.yml platform-frontend.yml.bak
#
# Routes:
#   hostingguard.lat     → frontend:80
#   www.hostingguard.lat → frontend:80
#
# No ForwardAuth — the SPA handles auth state client-side.
# ForwardAuth (hg-forwardauth) is ONLY for tenant site routers.

http:
  routers:
    platform-frontend:
      rule: "Host(`hostingguard.lat`) || Host(`www.hostingguard.lat`)"
      entryPoints:
        - websecure
      service: platform-frontend
      tls:
        certResolver: le
      priority: 100

  services:
    platform-frontend:
      loadBalancer:
        servers:
          - url: "http://frontend:80"
'

if [ -z "$CHECK_ONLY" ]; then
    printf '%s' "$FRONTEND_CONTENT" > "$FRONTEND_FILE"
    log_ok "Written: $FRONTEND_FILE"
else
    if [ -f "$FRONTEND_FILE" ]; then
        log_ok "Exists: $FRONTEND_FILE"
    else
        log_fail "Missing: $FRONTEND_FILE"
    fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# 3. platform-api.yml
#    Route: api.hostingguard.lat → hosting_guard:8000
#    No ForwardAuth — FastAPI handles JWT auth internally.
# ─────────────────────────────────────────────────────────────────────────────
API_FILE="$DYNAMIC_DIR/platform-api.yml"
API_CONTENT='# platform-api.yml
# Platform router for the FastAPI backend.
# Managed by scripts/ensure_platform_traefik_routes.sh — do not edit manually.
# Backup before editing: cp platform-api.yml platform-api.yml.bak
#
# Route:
#   api.hostingguard.lat → hosting_guard:8000
#
# No ForwardAuth — the FastAPI app handles JWT + 2FA internally.
# ForwardAuth (hg-forwardauth) is ONLY for tenant site routers (custom domains).
# NEVER add hg-forwardauth to this router — it would block all API calls.

http:
  routers:
    platform-api:
      rule: "Host(`api.hostingguard.lat`)"
      entryPoints:
        - websecure
      service: platform-api
      tls:
        certResolver: le
      priority: 100

  services:
    platform-api:
      loadBalancer:
        servers:
          - url: "http://hosting_guard:8000"
        responseForwarding:
          flushInterval: "100ms"
'

if [ -z "$CHECK_ONLY" ]; then
    printf '%s' "$API_CONTENT" > "$API_FILE"
    log_ok "Written: $API_FILE"
else
    if [ -f "$API_FILE" ]; then
        log_ok "Exists: $API_FILE"
    else
        log_fail "Missing: $API_FILE"
    fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# 4. Verify Traefik is running
# ─────────────────────────────────────────────────────────────────────────────
log_head "=== Infrastructure checks ==="

if docker inspect traefik &>/dev/null 2>&1; then
    log_ok "Traefik container running"
else
    log_fail "Traefik container not found (docker inspect traefik failed)"
fi

if docker inspect hosting_guard &>/dev/null 2>&1; then
    log_ok "App container (hosting_guard) running"
else
    log_fail "App container (hosting_guard) not found"
fi

if docker inspect frontend &>/dev/null 2>&1; then
    log_ok "Frontend container running"
else
    log_fail "Frontend container not found"
fi

# Give Traefik time to pick up file changes (file watch polling interval ~100ms)
if [ -z "$CHECK_ONLY" ]; then
    sleep 2
fi

# ─────────────────────────────────────────────────────────────────────────────
# 5. Internal connectivity (app responds on port 8000)
# ─────────────────────────────────────────────────────────────────────────────
log_head "=== Internal health ==="

if docker inspect hosting_guard &>/dev/null 2>&1; then
    INTERNAL_STATUS=$(docker exec hosting_guard \
        python3 -c "
import urllib.request, sys
try:
    r = urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5)
    print(r.status)
except Exception as e:
    print('ERR:' + str(e))
    sys.exit(1)
" 2>/dev/null || echo "000")

    if [ "$INTERNAL_STATUS" = "200" ]; then
        log_ok "App internal /health → 200"
    else
        log_fail "App internal /health → $INTERNAL_STATUS"
    fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# 6. Public endpoint checklist
# ─────────────────────────────────────────────────────────────────────────────
log_head "=== Public endpoint checks ==="

check_url() {
    local url="$1"
    local status
    status=$(curl -fsS -o /dev/null -w "%{http_code}" \
        --max-time 15 \
        --retry 2 \
        --retry-delay 1 \
        "$url" 2>/dev/null || echo "000")

    if [ "$status" = "200" ]; then
        log_ok "$url → $status"
    else
        log_fail "$url → $status  (expected 200)"
    fi
}

check_url "https://api.hostingguard.lat/health"
check_url "https://hostingguard.lat/"
check_url "https://hostingguard.lat/login"
check_url "https://hostingguard.lat/dashboard"

# ─────────────────────────────────────────────────────────────────────────────
# 7. Summary
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "────────────────────────────────────────────────────────────"

if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}${BOLD}FAIL${NC} — $FAIL check(s) failed, $PASS passed"
    echo ""
    echo "  Troubleshoot:"
    echo "    # Traefik logs"
    echo "    docker logs traefik --since=2m | grep -iE 'error|api.hostingguard|platform|frontend'"
    echo ""
    echo "    # App internal check"
    echo "    docker exec hosting_guard python3 -c \\"
    echo "      \"import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').status)\""
    echo ""
    echo "    # Verify dynamic files exist and are valid YAML"
    echo "    ls -la $DYNAMIC_DIR/platform-*.yml"
    echo "    python3 -c \"import yaml; yaml.safe_load(open('$API_FILE'))\" && echo 'API YAML OK'"
    echo "    python3 -c \"import yaml; yaml.safe_load(open('$FRONTEND_FILE'))\" && echo 'Frontend YAML OK'"
    echo ""
    exit 1
else
    echo -e "${GREEN}${BOLD}ALL OK${NC} — $PASS checks passed"
    echo ""
    echo "  Platform routes active:"
    echo "    hostingguard.lat / www → frontend:80"
    echo "    api.hostingguard.lat   → hosting_guard:8000"
    echo ""
    echo "  Dynamic files:"
    echo "    $FRONTEND_FILE"
    echo "    $API_FILE"
fi
