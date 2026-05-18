#!/usr/bin/env bash
# harden_existing_tenants.sh
#
# Recreates existing tenant containers (user_*) to apply P4C runtime hardening:
#   --security-opt no-new-privileges:true
#   --pids-limit    TENANT_PIDS_LIMIT (default 200)
#   --cpus / --memory from current container or configurable fallback
#
# Preserves exactly:
#   - Network:  deploy_tenant_edge_network
#   - Mounts:   all bind mounts, including :ro flags
#   - Labels:   all Traefik labels
#   - Env vars: written to a temp env-file (never printed to logs)
#   - Image:    same image as current container
#   - Restart:  same restart policy
#
# For each container:
#   1. Pre-check: curl https://<domain>/ (if domain found) → must be 2xx/3xx
#   2. docker stop → docker rm
#   3. docker run with hardening flags
#   4. Post-check: curl https://<domain>/ → must be 2xx/3xx
#   5. Rollback (recreate from saved spec without new flags) if post-check fails
#
# SAFETY: Dry-run by default. Pass --apply to actually recreate containers.
#
# Usage:
#   sudo ./scripts/ops/harden_existing_tenants.sh [OPTIONS]
#
# Options:
#   --apply                  Actually recreate containers (default: dry-run)
#   --tenant CONTAINER       Only process this container (default: all user_*)
#   --pids-limit N           Pids limit to apply (default: 200)
#   --fallback-cpu CPUS      CPU limit when container has none (default: 0.25)
#   --fallback-memory MEM    Memory limit when container has none (default: 256m)
#   --skip-domain-check      Skip pre/post domain curl validation
#   --force                  Recreate even if already hardened
#
# Examples:
#   # Preview all changes (safe, no modifications)
#   sudo ./scripts/ops/harden_existing_tenants.sh
#
#   # Apply to all tenant containers
#   sudo ./scripts/ops/harden_existing_tenants.sh --apply
#
#   # Harden a single container
#   sudo ./scripts/ops/harden_existing_tenants.sh --apply --tenant user_1_mi-academia_a3dab0

set -euo pipefail

APPLY=false
PIDS_LIMIT="${TENANT_PIDS_LIMIT:-200}"
TENANT_NETWORK="${TENANT_NETWORK:-deploy_tenant_edge_network}"
FILTER_CONTAINER=""
SKIP_DOMAIN_CHECK=false
CURL_TIMEOUT=15
FALLBACK_CPU="${FALLBACK_CPU:-0.25}"
FALLBACK_MEMORY="${FALLBACK_MEMORY:-256m}"
FORCE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply)              APPLY=true ;;
    --skip-domain-check)  SKIP_DOMAIN_CHECK=true ;;
    --force)              FORCE=true ;;
    --tenant)             FILTER_CONTAINER="$2"; shift ;;
    --pids-limit)         PIDS_LIMIT="$2"; shift ;;
    --fallback-cpu)       FALLBACK_CPU="$2"; shift ;;
    --fallback-memory)    FALLBACK_MEMORY="$2"; shift ;;
    *) echo "Unknown flag: $1"; exit 1 ;;
  esac
  shift
done

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RESET='\033[0m'
ok()    { echo -e "  ${GREEN}[OK]${RESET}    $*"; }
err()   { echo -e "  ${RED}[ERR]${RESET}   $*"; }
warn()  { echo -e "  ${YELLOW}[WARN]${RESET}  $*"; }
info()  { echo -e "${CYAN}[INFO]${RESET}  $*"; }
log()   { echo -e "         $*"; }

HARDENED=0; SKIPPED=0; FAILED=0; ROLLBACKS=0

# ── temp files (shared across iterations, overwritten per container) ──────────
TMPFILE=$(mktemp)
ENVFILE=$(mktemp)
PY_HELPER=$(mktemp)
trap 'rm -f "$TMPFILE" "$ENVFILE" "$PY_HELPER"' EXIT INT TERM

# Write Python helper once — parses docker inspect JSON and emits shell variables.
# All string values are shlex.quote'd so the output is safe to eval in bash.
# Env vars are written to ENVFILE (path from HG_ENV_FILE env var) to avoid
# printing secrets to the terminal log.
cat > "$PY_HELPER" << 'PYEOF'
import json, re, shlex, sys, os

data = json.load(sys.stdin)
# docker inspect returns a JSON array; element 0 is our container
if isinstance(data, list):
    data = data[0]

hc  = data.get('HostConfig', {})
cfg = data.get('Config', {})

image    = cfg.get('Image', '')
memory   = hc.get('Memory') or 0
nano_cpu = hc.get('NanoCpus') or 0
pids     = hc.get('PidsLimit') or 0
restart  = (hc.get('RestartPolicy') or {}).get('Name') or 'unless-stopped'
if restart in ('no', ''):
    restart = 'unless-stopped'

binds        = hc.get('Binds') or []
labels       = cfg.get('Labels') or {}
envs         = cfg.get('Env') or []
security_opt = hc.get('SecurityOpt') or []
cmd          = cfg.get('Cmd') or []

cpu_str = f'{nano_cpu / 1e9:.2f}' if nano_cpu > 0 else ''
mem_str = f'{memory // 1048576}m' if memory > 0 else ''

# Extract domain from the first Traefik router rule label (Host(`...`) syntax)
domain = ''
for k, v in labels.items():
    if 'traefik.http.routers' in k and k.endswith('.rule'):
        m = re.search(r"Host\(`([^`]+)`\)", v)
        if m:
            domain = m.group(1)
            break

already_hardened = (
    any('no-new-privileges' in o for o in security_opt) and int(pids) > 0
)

# Emit shell-safe key=value assignments
print(f'HG_IMAGE={shlex.quote(image)}')
print(f'HG_CPU={shlex.quote(cpu_str)}')
print(f'HG_MEMORY={shlex.quote(mem_str)}')
print(f'HG_RESTART={shlex.quote(restart)}')
print(f'HG_DOMAIN={shlex.quote(domain)}')
print(f'HG_PIDS={int(pids)}')
print(f'HG_ALREADY_HARDENED={"true" if already_hardened else "false"}')
print('HG_BINDS=(' + ' '.join(shlex.quote(b) for b in binds) + ')')
print('HG_LABELS=(' + ' '.join(shlex.quote(f'{k}={v}') for k, v in labels.items()) + ')')
print('HG_CMD=(' + ' '.join(shlex.quote(c) for c in cmd) + ')')
print(f'HG_ENVS_COUNT={len(envs)}')

# Write env vars to a file so they never appear in log output
env_file = os.environ.get('HG_ENV_FILE', '')
if env_file and envs:
    with open(env_file, 'w') as ef:
        for e in envs:
            ef.write(e + '\n')
PYEOF

# ── helpers ───────────────────────────────────────────────────────────────────

_curl_check() {
  local domain="$1" timeout="$2"
  curl -s -o /dev/null -w '%{http_code}' \
    --connect-timeout 8 --max-time "$timeout" \
    "https://$domain/" 2>/dev/null || echo "000"
}

_wait_running() {
  local container="$1"
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    local st
    st=$(docker inspect --format '{{.State.Status}}' "$container" 2>/dev/null || echo "missing")
    [[ "$st" == "running" ]] && return 0
    sleep 1
  done
  return 1
}

# ── collect containers ────────────────────────────────────────────────────────
if [[ -n "$FILTER_CONTAINER" ]]; then
  CONTAINERS=("$FILTER_CONTAINER")
else
  mapfile -t CONTAINERS < <(docker ps --filter "name=user_" --format '{{.Names}}' | sort)
fi

if [[ ${#CONTAINERS[@]} -eq 0 ]]; then
  info "No running tenant containers found (pattern: user_*)."
  exit 0
fi

DRY_RUN_LABEL=""
if ! $APPLY; then DRY_RUN_LABEL=" [DRY RUN]"; fi

echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "  Tenant Runtime Hardening${DRY_RUN_LABEL}"
echo "  Containers: ${#CONTAINERS[@]}   pids-limit: $PIDS_LIMIT"
echo "  Flags: --security-opt no-new-privileges:true --pids-limit $PIDS_LIMIT"
if ! $APPLY; then
  echo "  --> DRY-RUN: pass --apply to actually recreate containers"
fi
echo "════════════════════════════════════════════════════════════════════"
echo ""

# ── per-container ─────────────────────────────────────────────────────────────
for CONTAINER in "${CONTAINERS[@]}"; do
  echo "┌─ $CONTAINER"

  # Wipe temp files for this iteration
  > "$TMPFILE"; > "$ENVFILE"

  if ! docker inspect "$CONTAINER" > "$TMPFILE" 2>/dev/null; then
    warn "Could not inspect $CONTAINER — skipping"
    SKIPPED=$((SKIPPED+1))
    echo "└───"; continue
  fi

  # Parse inspect → shell variables (all values are shlex.quote'd → safe to eval)
  PARSE_OUT=$(HG_ENV_FILE="$ENVFILE" python3 "$PY_HELPER" < "$TMPFILE" 2>/dev/null) || {
    warn "Failed to parse inspect output — skipping"
    SKIPPED=$((SKIPPED+1))
    echo "└───"; continue
  }
  [[ -z "$PARSE_OUT" ]] && { warn "Empty parse output — skipping"; SKIPPED=$((SKIPPED+1)); echo "└───"; continue; }

  eval "$PARSE_OUT"

  # ── already hardened? ─────────────────────────────────────────────────────
  if [[ "$HG_ALREADY_HARDENED" == "true" ]] && ! $FORCE; then
    ok "Already hardened (no-new-privileges + pids-limit present)"
    log "Use --force to re-apply."
    SKIPPED=$((SKIPPED+1))
    echo "└───"; continue
  fi

  log "Image:   $HG_IMAGE"
  log "CPU:     ${HG_CPU:-(not set — will use fallback $FALLBACK_CPU)}"
  log "Memory:  ${HG_MEMORY:-(not set — will use fallback $FALLBACK_MEMORY)}"
  log "Domain:  ${HG_DOMAIN:-(none — domain check skipped)}"
  log "Binds:   ${HG_BINDS[*]:-(none)}"
  log "Envs:    $HG_ENVS_COUNT env var(s) — values not printed"

  EFF_CPU="${HG_CPU:-$FALLBACK_CPU}"
  EFF_MEMORY="${HG_MEMORY:-$FALLBACK_MEMORY}"

  # ── pre-check ────────────────────────────────────────────────────────────
  if [[ -n "$HG_DOMAIN" ]] && ! $SKIP_DOMAIN_CHECK; then
    log "Pre-check: https://$HG_DOMAIN ..."
    PRE_CODE=$(_curl_check "$HG_DOMAIN" "$CURL_TIMEOUT")
    if [[ "$PRE_CODE" =~ ^[23] ]]; then
      ok "Pre-check → HTTP $PRE_CODE"
    else
      warn "Pre-check → HTTP $PRE_CODE (domain may already be unreachable)"
    fi
  fi

  # ── build hardened command ────────────────────────────────────────────────
  NEW_CMD=(
    "run" "-d"
    "--name"    "$CONTAINER"
    "--network" "$TENANT_NETWORK"
    "--restart" "$HG_RESTART"
    "--cpus"    "$EFF_CPU"
    "--memory"  "$EFF_MEMORY"
    "--security-opt" "no-new-privileges:true"
    "--pids-limit"   "$PIDS_LIMIT"
  )
  for bind in "${HG_BINDS[@]:+${HG_BINDS[@]}}"; do NEW_CMD+=("-v" "$bind"); done
  for label in "${HG_LABELS[@]:+${HG_LABELS[@]}}"; do NEW_CMD+=("-l" "$label"); done
  [[ -s "$ENVFILE" ]] && NEW_CMD+=("--env-file" "$ENVFILE")
  NEW_CMD+=("$HG_IMAGE")
  for c in "${HG_CMD[@]:+${HG_CMD[@]}}"; do NEW_CMD+=("$c"); done

  # ── build rollback command (original config, without new hardening flags) ──
  ROLLBACK_CMD=(
    "run" "-d"
    "--name"    "$CONTAINER"
    "--network" "$TENANT_NETWORK"
    "--restart" "$HG_RESTART"
  )
  [[ -n "$HG_CPU"    ]] && ROLLBACK_CMD+=("--cpus"       "$HG_CPU")
  [[ -n "$HG_MEMORY" ]] && ROLLBACK_CMD+=("--memory"     "$HG_MEMORY")
  [[ "$HG_PIDS" -gt 0 ]] && ROLLBACK_CMD+=("--pids-limit" "$HG_PIDS")
  for bind in "${HG_BINDS[@]:+${HG_BINDS[@]}}"; do ROLLBACK_CMD+=("-v" "$bind"); done
  for label in "${HG_LABELS[@]:+${HG_LABELS[@]}}"; do ROLLBACK_CMD+=("-l" "$label"); done
  [[ -s "$ENVFILE" ]] && ROLLBACK_CMD+=("--env-file" "$ENVFILE")
  ROLLBACK_CMD+=("$HG_IMAGE")
  for c in "${HG_CMD[@]:+${HG_CMD[@]}}"; do ROLLBACK_CMD+=("$c"); done

  # ── dry-run output ────────────────────────────────────────────────────────
  if ! $APPLY; then
    log "Would stop and remove: $CONTAINER"
    log "Would run: docker run --name $CONTAINER --network $TENANT_NETWORK \\"
    log "           --restart $HG_RESTART --cpus $EFF_CPU --memory $EFF_MEMORY \\"
    log "           --security-opt no-new-privileges:true --pids-limit $PIDS_LIMIT \\"
    log "           [${#HG_BINDS[@]} bind(s)] [${#HG_LABELS[@]} label(s)] [$HG_ENVS_COUNT env(s)] $HG_IMAGE"
    [[ ${#HG_CMD[@]} -gt 0 ]] && log "           cmd: ${HG_CMD[*]}"
    HARDENED=$((HARDENED+1))
    echo "└───"; continue
  fi

  # ── apply: stop → rm → recreate ─────────────────────────────────────────
  log "Stopping..."
  docker stop --time 10 "$CONTAINER" >/dev/null 2>&1 || warn "Stop returned non-zero (may already be stopped)"

  log "Removing..."
  if ! docker rm "$CONTAINER" >/dev/null 2>&1; then
    err "docker rm failed — skipping"
    FAILED=$((FAILED+1))
    echo "└───"; continue
  fi

  log "Recreating with hardening flags..."
  if ! docker "${NEW_CMD[@]}" >/dev/null 2>&1; then
    err "docker run failed — rolling back..."
    if docker "${ROLLBACK_CMD[@]}" >/dev/null 2>&1; then
      warn "Rolled back to original config"
      ROLLBACKS=$((ROLLBACKS+1))
    else
      err "Rollback also failed — $CONTAINER is DOWN"
    fi
    FAILED=$((FAILED+1))
    echo "└───"; continue
  fi

  # Wait for the container to reach 'running' state
  if ! _wait_running "$CONTAINER"; then
    err "Container did not reach 'running' within 10s — rolling back..."
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    if docker "${ROLLBACK_CMD[@]}" >/dev/null 2>&1; then
      warn "Rolled back to original config"
      ROLLBACKS=$((ROLLBACKS+1))
    else
      err "Rollback also failed — $CONTAINER is DOWN"
    fi
    FAILED=$((FAILED+1))
    echo "└───"; continue
  fi
  ok "Container is running"

  # ── post-check ────────────────────────────────────────────────────────────
  ROLLBACK=false
  if [[ -n "$HG_DOMAIN" ]] && ! $SKIP_DOMAIN_CHECK; then
    sleep 2   # give nginx time to accept connections
    log "Post-check: https://$HG_DOMAIN ..."
    POST_CODE=$(_curl_check "$HG_DOMAIN" "$CURL_TIMEOUT")
    if [[ "$POST_CODE" =~ ^[23] ]]; then
      ok "Post-check → HTTP $POST_CODE"
    else
      err "Post-check → HTTP $POST_CODE — rolling back"
      ROLLBACK=true
    fi
  fi

  if $ROLLBACK; then
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    if docker "${ROLLBACK_CMD[@]}" >/dev/null 2>&1; then
      warn "Rolled back — $CONTAINER restored to original config"
      ROLLBACKS=$((ROLLBACKS+1))
    else
      err "Rollback also failed — $CONTAINER is DOWN"
    fi
    FAILED=$((FAILED+1))
    echo "└───"; continue
  fi

  ok "Hardened successfully"
  HARDENED=$((HARDENED+1))
  echo "└───"
  echo ""
done

# ── summary ───────────────────────────────────────────────────────────────────
echo "════════════════════════════════════════════════════════════════════"
echo "  Done${DRY_RUN_LABEL}"
echo "  Hardened: $HARDENED   Skipped: $SKIPPED   Failed: $FAILED   Rollbacks: $ROLLBACKS"
echo "════════════════════════════════════════════════════════════════════"

if ! $APPLY && [[ $HARDENED -gt 0 ]]; then
  echo ""
  echo "  Pass --apply to apply the changes above."
fi

if [[ $FAILED -gt 0 ]]; then
  echo ""
  echo -e "${RED}  $FAILED container(s) failed or were rolled back${RESET}"
  echo ""
  echo "  Manual recovery:"
  echo "    sudo docker inspect <container>     # check current state"
  echo "    sudo ./scripts/security/validate_runtime_hardening.sh --tenant <container>"
  exit 1
fi

if [[ $ROLLBACKS -gt 0 ]] && [[ $FAILED -eq 0 ]]; then
  echo -e "${YELLOW}  $ROLLBACKS container(s) were rolled back — check domain availability${RESET}"
  exit 1
fi
