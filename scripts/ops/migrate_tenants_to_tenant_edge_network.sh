#!/usr/bin/env bash
# migrate_tenants_to_tenant_edge_network.sh
#
# Migrates existing tenant containers (user_*) from deploy_hosting_network to
# deploy_tenant_edge_network (P4B network isolation hardening).
#
# For each tenant container:
#   1. Connect to tenant_edge_network
#   2. Verify Traefik labels (warn if missing, do not block)
#   3. Validate public domain if --domain-check is set
#   4. Disconnect from platform/hosting network
#   5. Rollback (reconnect old network) if domain check fails
#
# Usage:
#   sudo ./scripts/ops/migrate_tenants_to_tenant_edge_network.sh [OPTIONS]
#
# Options:
#   --dry-run                    Print what would happen, no changes.
#   --domain-check               After connect, curl https://<domain>/ to verify Traefik routing.
#   --require-domain-validation  Exit with error if domain cannot be determined for a container.

set -euo pipefail

PLATFORM_NETWORK="${PLATFORM_NETWORK:-deploy_hosting_network}"
TENANT_NETWORK="${TENANT_NETWORK:-deploy_tenant_edge_network}"
TRAEFIK_DYNAMIC_DIR="${TRAEFIK_DYNAMIC_DIR:-/opt/traefik-dynamic}"
DRY_RUN=false
DOMAIN_CHECK=false
REQUIRE_DOMAIN=false

for arg in "$@"; do
  case "$arg" in
    --dry-run)                    DRY_RUN=true ;;
    --domain-check)               DOMAIN_CHECK=true ;;
    --require-domain-validation)  REQUIRE_DOMAIN=true; DOMAIN_CHECK=true ;;
    *) echo "Unknown flag: $arg"; exit 1 ;;
  esac
done

# ── dry-run label (correct: test the actual boolean, not string non-emptiness) ─
DRY_RUN_LABEL=""
if $DRY_RUN; then DRY_RUN_LABEL=" [DRY RUN]"; fi

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RESET='\033[0m'
ok()   { echo -e "  ${GREEN}[OK]${RESET}    $*"; }
err()  { echo -e "  ${RED}[ERR]${RESET}   $*"; }
warn() { echo -e "  ${YELLOW}[WARN]${RESET}  $*"; }
info() { echo -e "${CYAN}[INFO]${RESET}  $*"; }
log()  { echo -e "         $*"; }

MIGRATED=0; SKIPPED=0; FAILED=0; ROLLBACKS=0

# ── ensure tenant_edge_network exists ────────────────────────────────────────
if ! docker network ls --format '{{.Name}}' | grep -qx "$TENANT_NETWORK"; then
  if $DRY_RUN; then
    warn "Network $TENANT_NETWORK does not exist (would create)"
  else
    info "Creating $TENANT_NETWORK..."
    docker network create "$TENANT_NETWORK"
    ok "Created $TENANT_NETWORK"
  fi
fi

# ── collect tenant containers ─────────────────────────────────────────────────
mapfile -t CONTAINERS < <(docker ps --filter "name=user_" --format '{{.Names}}' | sort)

if [[ ${#CONTAINERS[@]} -eq 0 ]]; then
  info "No running tenant containers found (pattern: user_*)."
  exit 0
fi

echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "  Tenant Network Migration${DRY_RUN_LABEL}"
echo "  From: $PLATFORM_NETWORK → To: $TENANT_NETWORK"
echo "  Containers: ${#CONTAINERS[@]}"
echo "════════════════════════════════════════════════════════════════════"
echo ""

# ── domain extraction (POSIX-compatible, no lookbehind) ──────────────────────
#
# Traefik rule label value looks like:  Host(`foo.hostingguard.lat`)
# We split on the backtick character (ASCII 0x60) with awk and take field 2.
# No grep -P / no lookahead / no PCRE needed.
_extract_domain_from_rule() {
  # $1 = raw rule string, e.g. Host(`foo.example.com`) or Host(`a`) || Host(`b`)
  echo "$1" | awk 'BEGIN{FS="`"} NF>=2{print $2; exit}'
}

# Try all three sources in order, return first non-empty domain found.
_get_domain() {
  local cname="$1"
  local rule domain

  # 1. Docker label: traefik.http.routers.<container>.rule
  rule=$(docker inspect \
    --format '{{range $k,$v := .Config.Labels}}{{$k}}={{$v}}
{{end}}' \
    "$cname" 2>/dev/null \
    | grep "traefik.http.routers.*\.rule=" \
    | head -1 \
    | sed 's/^[^=]*=//')
  if [[ -n "$rule" ]]; then
    domain=$(_extract_domain_from_rule "$rule")
    if [[ -n "$domain" ]]; then echo "$domain"; return; fi
  fi

  # 2. Traefik dynamic YAML file that references this container
  if [[ -d "$TRAEFIK_DYNAMIC_DIR" ]]; then
    local yaml_file
    yaml_file=$(grep -rl "\"$cname\"\|'$cname'" "$TRAEFIK_DYNAMIC_DIR" 2>/dev/null | head -1 || true)
    if [[ -n "$yaml_file" ]]; then
      domain=$(grep -m1 "rule:" "$yaml_file" 2>/dev/null \
        | sed 's/.*rule:[[:space:]]*//' \
        | awk 'BEGIN{FS="`"} NF>=2{print $2; exit}')
      if [[ -n "$domain" ]]; then echo "$domain"; return; fi
    fi
  fi

  # 3. Infer from container name: user_<uid>_[wp_]<name>_<hex> → <name>.hostingguard.lat
  # Strip leading user_<uid>_ and trailing _<6hex>, remove wp_/db_ type prefix.
  local base name_part
  base=$(echo "$cname" | sed 's/^user_[0-9]*_//' | sed 's/_[0-9a-f]\{6\}$//')
  name_part=$(echo "$base" | sed 's/^wp_//;s/^db_//')
  if [[ -n "$name_part" ]]; then
    echo "${name_part}.hostingguard.lat"
    return
  fi
}

# ── per-container migration ───────────────────────────────────────────────────
for CONTAINER in "${CONTAINERS[@]}"; do
  echo "┌─ $CONTAINER"

  NETWORKS=$(docker inspect --format \
    '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' \
    "$CONTAINER" 2>/dev/null | tr ' ' '\n' | grep -v '^$' || true)

  ON_TENANT=$(echo "$NETWORKS" | grep -cx "^${TENANT_NETWORK}$" || true)
  ON_PLATFORM=$(echo "$NETWORKS" | grep -cx "^${PLATFORM_NETWORK}$" || true)

  # ── already migrated? ─────────────────────────────────────────────────────
  if [[ "$ON_TENANT" -gt 0 ]] && [[ "$ON_PLATFORM" -eq 0 ]]; then
    ok "Already isolated — skipping"
    SKIPPED=$((SKIPPED+1))
    echo "└───"; continue
  fi

  if [[ "$ON_PLATFORM" -eq 0 ]]; then
    warn "Not on $PLATFORM_NETWORK — skipping"
    log "Networks: $(echo "$NETWORKS" | tr '\n' ' ')"
    SKIPPED=$((SKIPPED+1))
    echo "└───"; continue
  fi

  if $DRY_RUN; then
    log "Would: docker network connect $TENANT_NETWORK $CONTAINER"
    log "Would: docker network disconnect $PLATFORM_NETWORK $CONTAINER"
    MIGRATED=$((MIGRATED+1))
    echo "└───"; continue
  fi

  # ── step 1: connect to tenant_edge_network ───────────────────────────────
  if [[ "$ON_TENANT" -eq 0 ]]; then
    if ! docker network connect "$TENANT_NETWORK" "$CONTAINER" 2>/dev/null; then
      err "docker network connect $TENANT_NETWORK failed — skipping"
      FAILED=$((FAILED+1))
      echo "└───"; continue
    fi
    ok "Connected to $TENANT_NETWORK"
  else
    log "Already on $TENANT_NETWORK"
  fi

  # ── step 2: Traefik label audit (warn only) ──────────────────────────────
  TRAEFIK_ENABLED=$(docker inspect --format \
    '{{index .Config.Labels "traefik.enable"}}' "$CONTAINER" 2>/dev/null || true)
  if [[ "$TRAEFIK_ENABLED" == "true" ]]; then
    ok "traefik.enable=true"
  else
    warn "traefik.enable label missing — Traefik won't route (container needs recreation)"
  fi

  TRAEFIK_NET=$(docker inspect --format \
    '{{index .Config.Labels "traefik.docker.network"}}' "$CONTAINER" 2>/dev/null || true)
  if [[ "$TRAEFIK_NET" == "$TENANT_NETWORK" ]]; then
    ok "traefik.docker.network=$TENANT_NETWORK"
  else
    warn "traefik.docker.network='${TRAEFIK_NET:-<missing>}' (should be $TENANT_NETWORK — needs recreation)"
  fi

  # ── step 3: optional domain validation ──────────────────────────────────
  ROLLBACK=false
  if $DOMAIN_CHECK; then
    DOMAIN=$(_get_domain "$CONTAINER")
    if [[ -n "$DOMAIN" ]]; then
      log "Checking https://$DOMAIN ..."
      HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' \
        --connect-timeout 8 --max-time 15 \
        "https://$DOMAIN/" 2>/dev/null || echo "000")
      if [[ "$HTTP_CODE" =~ ^[23] ]]; then
        ok "https://$DOMAIN → HTTP $HTTP_CODE"
      else
        err "https://$DOMAIN → HTTP $HTTP_CODE — rolling back"
        ROLLBACK=true
      fi
    else
      if $REQUIRE_DOMAIN; then
        err "Cannot determine domain for $CONTAINER (--require-domain-validation set)"
        ROLLBACK=true
      else
        warn "Cannot determine domain — skipping domain check (use --require-domain-validation to fail)"
      fi
    fi
  fi

  if $ROLLBACK; then
    docker network disconnect "$TENANT_NETWORK" "$CONTAINER" 2>/dev/null || true
    err "Rolled back — $CONTAINER remains on $PLATFORM_NETWORK"
    ROLLBACKS=$((ROLLBACKS+1))
    FAILED=$((FAILED+1))
    echo "└───"; continue
  fi

  # ── step 4: disconnect from platform network ─────────────────────────────
  if docker network disconnect "$PLATFORM_NETWORK" "$CONTAINER" 2>/dev/null; then
    ok "Disconnected from $PLATFORM_NETWORK"
  else
    warn "Could not disconnect from $PLATFORM_NETWORK (may already be absent)"
  fi

  ok "Migrated"
  MIGRATED=$((MIGRATED+1))
  echo "└───"
  echo ""
done

# ── summary ───────────────────────────────────────────────────────────────────
echo "════════════════════════════════════════════════════════════════════"
echo "  Migration complete${DRY_RUN_LABEL}"
echo "  Migrated:  $MIGRATED   Skipped: $SKIPPED   Failed: $FAILED   Rollbacks: $ROLLBACKS"
echo "════════════════════════════════════════════════════════════════════"

if [[ $FAILED -gt 0 ]]; then
  echo ""
  echo -e "${RED}  $FAILED container(s) failed — check errors above${RESET}"
  echo ""
  echo "  Manual rollback for a single container:"
  echo "    sudo docker network connect $PLATFORM_NETWORK <container>"
  echo "    sudo docker network disconnect $TENANT_NETWORK <container>"
  exit 1
fi

if [[ $MIGRATED -gt 0 ]] && ! $DRY_RUN; then
  echo ""
  info "Validate isolation:"
  echo "  sudo ./scripts/security/validate_tenant_network_isolation.sh <container> --domain <domain>"
fi
