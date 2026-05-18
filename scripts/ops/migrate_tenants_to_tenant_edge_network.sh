#!/usr/bin/env bash
# migrate_tenants_to_tenant_edge_network.sh
#
# Migrates existing tenant containers from deploy_hosting_network to
# deploy_tenant_edge_network (network isolation hardening — P4B).
#
# For each user_* container:
#   1. Connect to tenant_edge_network
#   2. Validate the public domain responds via curl
#   3. Disconnect from hosting_network
#   4. Rollback (reconnect hosting_network) if validation fails
#
# Usage:
#   ./scripts/ops/migrate_tenants_to_tenant_edge_network.sh [--dry-run]
#
# Flags:
#   --dry-run   Print what would happen without making any changes.

set -euo pipefail

PLATFORM_NETWORK="${PLATFORM_NETWORK:-deploy_hosting_network}"
TENANT_NETWORK="${TENANT_NETWORK:-deploy_tenant_edge_network}"
DRY_RUN=false

for arg in "$@"; do
  [[ "$arg" == "--dry-run" ]] && DRY_RUN=true
done

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RESET='\033[0m'
ok()   { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn() { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
err()  { echo -e "${RED}[ERROR]${RESET} $*"; }
info() { echo -e "${CYAN}[INFO]${RESET}  $*"; }

MIGRATED=0; SKIPPED=0; FAILED=0

# ── ensure tenant_edge_network exists ────────────────────────────────────────
if ! docker network ls --format '{{.Name}}' | grep -qx "$TENANT_NETWORK"; then
  if $DRY_RUN; then
    warn "Network $TENANT_NETWORK does not exist (would create)"
  else
    info "Creating network $TENANT_NETWORK..."
    docker network create "$TENANT_NETWORK"
    ok "Created $TENANT_NETWORK"
  fi
fi

# ── collect tenant containers ─────────────────────────────────────────────────
mapfile -t CONTAINERS < <(docker ps --filter "name=user_" --format '{{.Names}}' | sort)

if [[ ${#CONTAINERS[@]} -eq 0 ]]; then
  info "No tenant containers found (pattern: user_*)."
  exit 0
fi

echo ""
echo "══════════════════════════════════════════════════════════════════"
echo "  Tenant Network Migration${DRY_RUN:+ [DRY RUN]}"
echo "  From: $PLATFORM_NETWORK"
echo "  To:   $TENANT_NETWORK"
echo "  Containers: ${#CONTAINERS[@]}"
echo "══════════════════════════════════════════════════════════════════"
echo ""

for CONTAINER in "${CONTAINERS[@]}"; do
  info "Processing: $CONTAINER"

  # Check current networks
  NETWORKS=$(docker inspect --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' "$CONTAINER" 2>/dev/null || echo "")

  # Already on tenant_edge_network?
  if echo "$NETWORKS" | grep -qw "$TENANT_NETWORK"; then
    # Already migrated — just ensure disconnected from platform network
    if echo "$NETWORKS" | grep -qw "$PLATFORM_NETWORK"; then
      if $DRY_RUN; then
        warn "  Would disconnect from $PLATFORM_NETWORK (already on $TENANT_NETWORK)"
      else
        docker network disconnect "$PLATFORM_NETWORK" "$CONTAINER" 2>/dev/null || true
        ok "  Disconnected from $PLATFORM_NETWORK (was already on $TENANT_NETWORK)"
      fi
    else
      ok "  Already isolated — skipping"
    fi
    SKIPPED=$((SKIPPED+1))
    continue
  fi

  # Not on platform network at all? Skip.
  if ! echo "$NETWORKS" | grep -qw "$PLATFORM_NETWORK"; then
    warn "  Not on $PLATFORM_NETWORK — skipping (networks: $NETWORKS)"
    SKIPPED=$((SKIPPED+1))
    continue
  fi

  if $DRY_RUN; then
    info "  [dry-run] Would connect to $TENANT_NETWORK then disconnect from $PLATFORM_NETWORK"
    MIGRATED=$((MIGRATED+1))
    continue
  fi

  # Resolve public domain from Traefik labels
  DOMAIN=$(docker inspect --format \
    '{{range $k,$v := .Config.Labels}}{{if (hasPrefix $k "traefik.http.routers.")}}{{if (hasSuffix $k ".rule")}}{{$v}}{{end}}{{end}}{{end}}' \
    "$CONTAINER" 2>/dev/null | grep -oP "(?<=Host\(`)([^`]+)" | head -1 || true)

  # Step 1: connect to new network
  info "  Connecting to $TENANT_NETWORK..."
  if ! docker network connect "$TENANT_NETWORK" "$CONTAINER"; then
    err "  Failed to connect $CONTAINER to $TENANT_NETWORK — skipping"
    FAILED=$((FAILED+1))
    continue
  fi

  # Step 2: validate public domain (if known)
  VALID=true
  if [[ -n "$DOMAIN" ]]; then
    info "  Validating https://$DOMAIN ..."
    HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' \
      --connect-timeout 8 --max-time 15 \
      --resolve "$DOMAIN:443:127.0.0.1" \
      "https://$DOMAIN/" 2>/dev/null || echo "000")
    if [[ "$HTTP_CODE" == "000" ]] || [[ "$HTTP_CODE" == "5"* ]]; then
      warn "  Validation returned HTTP $HTTP_CODE for $DOMAIN — rolling back"
      VALID=false
    else
      ok "  Domain $DOMAIN → HTTP $HTTP_CODE"
    fi
  else
    warn "  No Traefik domain label found — skipping domain validation"
  fi

  if ! $VALID; then
    # Rollback: disconnect from new network
    docker network disconnect "$TENANT_NETWORK" "$CONTAINER" 2>/dev/null || true
    err "  Rolled back $CONTAINER — still on $PLATFORM_NETWORK"
    FAILED=$((FAILED+1))
    continue
  fi

  # Step 3: disconnect from platform network
  info "  Disconnecting from $PLATFORM_NETWORK..."
  if ! docker network disconnect "$PLATFORM_NETWORK" "$CONTAINER"; then
    warn "  Could not disconnect from $PLATFORM_NETWORK (may already be disconnected)"
  fi

  ok "  Migrated: $CONTAINER"
  MIGRATED=$((MIGRATED+1))
  echo ""
done

echo ""
echo "══════════════════════════════════════════════════════════════════"
echo "  Migration complete${DRY_RUN:+ [DRY RUN]}"
echo "  Migrated:  $MIGRATED"
echo "  Skipped:   $SKIPPED"
echo "  Failed:    $FAILED"
echo "══════════════════════════════════════════════════════════════════"

if [[ $FAILED -gt 0 ]]; then
  echo ""
  err "$FAILED container(s) failed migration. Check the errors above."
  exit 1
fi

if [[ $MIGRATED -gt 0 ]] && ! $DRY_RUN; then
  echo ""
  info "Run the isolation validation to confirm:"
  echo "  ./scripts/security/validate_tenant_network_isolation.sh"
fi
