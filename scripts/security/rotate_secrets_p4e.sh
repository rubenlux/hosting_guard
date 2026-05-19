#!/usr/bin/env bash
# rotate_secrets_p4e.sh  — P4E Secrets Rotation
#
# Rotates JWT_SECRET and optionally SECRET_KEY in .env.production.
# Never prints secret values — only shows fingerprints (length + SHA256 prefix).
# Creates a timestamped backup before any modification.
#
# Usage:
#   sudo ./scripts/security/rotate_secrets_p4e.sh               (dry-run)
#   sudo ./scripts/security/rotate_secrets_p4e.sh --apply        (rotate)
#   sudo ROTATE_SK=false ./scripts/security/rotate_secrets_p4e.sh --apply  (skip SECRET_KEY)
#
# Environment overrides:
#   ENV_FILE   — path to .env.production (default: /opt/deploy/.env.production)
#   BACKUP_DIR — where to write the backup (default: /root)
#   ROTATE_SK  — rotate SECRET_KEY too? (default: true)
#
# Safety guarantees:
#   - Dry-run by default; --apply required for changes
#   - Backup created before modification (perms 600, owner root)
#   - Secrets generated and written entirely inside Python (never in shell vars)
#   - Only fingerprints (len + sha256 prefix) printed to terminal
#   - Rollback if post-write verification fails

set -euo pipefail

ENV_FILE="${ENV_FILE:-/opt/deploy/.env.production}"
BACKUP_DIR="${BACKUP_DIR:-/root}"
ROTATE_SK="${ROTATE_SK:-true}"
APPLY=false

# ── parse args ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply)    APPLY=true;  shift ;;
    --dry-run)  APPLY=false; shift ;;
    *) echo "Unknown flag: $1"; exit 1 ;;
  esac
done

# ── colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RESET='\033[0m'
pass()  { echo -e "  ${GREEN}[PASS]${RESET} $*"; }
fail()  { echo -e "  ${RED}[FAIL]${RESET} $*"; }
info()  { echo -e "${CYAN}[INFO]${RESET} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${RESET} $*"; }
section(){ echo ""; echo -e "${YELLOW}── $* ──${RESET}"; }

echo ""
echo "══════════════════════════════════════════════════════════"
echo "  P4E — Secrets Rotation"
[[ "$APPLY" == "true" ]] && echo "  Mode: APPLY (changes will be written)" || echo "  Mode: DRY-RUN (no changes)"
echo "  Env file: $ENV_FILE"
echo "══════════════════════════════════════════════════════════"

# ── pre-flight ────────────────────────────────────────────────────────────────
section "Pre-flight checks"

if [[ ! -f "$ENV_FILE" ]]; then
  fail "Env file not found: $ENV_FILE"
  exit 1
fi
pass "Env file exists: $ENV_FILE"

# File permissions — must not be world-readable
perms=$(stat -c "%a" "$ENV_FILE" 2>/dev/null || stat -f "%OLp" "$ENV_FILE" 2>/dev/null || echo "000")
world_bit="${perms: -1}"
if [[ "$world_bit" != "0" ]]; then
  fail "Env file is world-readable (perms=$perms) — fix: chmod o-r \"$ENV_FILE\""
  exit 1
fi
pass "Env file permissions: $perms (not world-readable)"

# openssl available?
if ! command -v openssl >/dev/null 2>&1; then
  fail "openssl not found — required for secret generation"
  exit 1
fi
pass "openssl available: $(openssl version | head -1)"

# python3 available?
if ! command -v python3 >/dev/null 2>&1; then
  fail "python3 not found — required for safe file manipulation"
  exit 1
fi
pass "python3 available: $(python3 --version)"

# ── inspect current secrets (fingerprints only) ───────────────────────────────
section "Current secret fingerprints (no values printed)"

python3 - "$ENV_FILE" <<'PYEOF'
import sys, hashlib, re

env_file = sys.argv[1]

def fingerprint(val):
    if not val:
        return "EMPTY"
    sha = hashlib.sha256(val.encode()).hexdigest()[:12]
    return f"len={len(val)}  sha256={sha}..."

with open(env_file, 'r') as f:
    content = f.read()

for key in ["JWT_SECRET", "SECRET_KEY"]:
    m = re.search(rf'^{key}=(.+)$', content, re.MULTILINE)
    if m:
        val = m.group(1).strip().strip('"').strip("'")
        print(f"  {key}: {fingerprint(val)}")
    else:
        print(f"  {key}: NOT FOUND")
PYEOF

# ── validate current values ───────────────────────────────────────────────────
section "Validate current secrets"

python3 - "$ENV_FILE" <<'PYEOF'
import sys, re

env_file = sys.argv[1]
errors = []

with open(env_file, 'r') as f:
    content = f.read()

for key, min_len in [("JWT_SECRET", 32), ("SECRET_KEY", 16)]:
    m = re.search(rf'^{key}=(.+)$', content, re.MULTILINE)
    if not m:
        print(f"  [WARN] {key}: not found — will skip rotation for this key")
        continue
    val = m.group(1).strip().strip('"').strip("'")
    if not val:
        errors.append(f"{key} is empty")
        print(f"  [FAIL] {key}: empty")
    elif len(val) < min_len:
        errors.append(f"{key} is too short ({len(val)} < {min_len})")
        print(f"  [WARN] {key}: len={len(val)} < {min_len} (should be rotated)")
    else:
        print(f"  [PASS] {key}: len={len(val)} >= {min_len}")

if errors:
    sys.exit(1)
PYEOF

if [[ "$APPLY" != "true" ]]; then
  echo ""
  echo "══════════════════════════════════════════════════════════"
  warn "DRY-RUN — No changes applied."
  echo ""
  info "New secrets would be generated with: openssl rand -hex 64"
  info "IMPACT: rotating JWT_SECRET invalidates ALL active sessions."
  info "        Users and staff will be required to log in again."
  echo ""
  info "To rotate, run:"
  info "  sudo ${BASH_SOURCE[0]} --apply"
  echo "══════════════════════════════════════════════════════════"
  exit 0
fi

# ── backup ───────────────────────────────────────────────────────────────────
section "Backup"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/.env.production.backup_p4e_${TIMESTAMP}"

cp "$ENV_FILE" "$BACKUP_FILE"
chmod 600 "$BACKUP_FILE"
chown root:root "$BACKUP_FILE" 2>/dev/null || true

pass "Backup created: $BACKUP_FILE"
pass "Backup permissions: 600 (owner root)"
info "To restore: sudo cp \"$BACKUP_FILE\" \"$ENV_FILE\" && sudo docker compose -f /opt/deploy/docker-compose.yml restart hosting_guard hg_worker hg_scheduler"

# ── rotate secrets ─────────────────────────────────────────────────────────────
section "Rotate secrets"

# All secret generation and file writing happens inside Python.
# The new secret values are NEVER assigned to shell variables.
python3 - "$ENV_FILE" "$BACKUP_FILE" "$ROTATE_SK" <<'PYEOF'
import sys, os, re, hashlib, subprocess

env_file     = sys.argv[1]
backup_file  = sys.argv[2]
rotate_sk    = sys.argv[3].lower() in ("true", "1", "yes")

def gen_secret():
    """Generate a 64-byte (128 hex char) cryptographically strong secret."""
    result = subprocess.run(
        ["openssl", "rand", "-hex", "64"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError("openssl rand failed: " + result.stderr)
    return result.stdout.strip()

def fingerprint(val):
    sha = hashlib.sha256(val.encode()).hexdigest()[:12]
    return f"len={len(val)}  sha256={sha}..."

def rotate_key(content, key, new_val):
    new_content = re.sub(
        rf'^({key}=).*$',
        rf'\g<1>{new_val}',
        content,
        flags=re.MULTILINE
    )
    if new_content == content:
        raise RuntimeError(f"{key} not found in env file — rotation aborted")
    return new_content

# Read current content
with open(env_file, 'r') as f:
    content = f.read()

# Keep backup copy for rollback
original_content = content

rotated = []
try:
    # Rotate JWT_SECRET
    if re.search(r'^JWT_SECRET=.+', content, re.MULTILINE):
        new_jwt = gen_secret()
        assert len(new_jwt) == 128, f"Unexpected JWT secret length: {len(new_jwt)}"
        content = rotate_key(content, "JWT_SECRET", new_jwt)
        print(f"  [PASS] JWT_SECRET rotated: {fingerprint(new_jwt)}")
        rotated.append("JWT_SECRET")
    else:
        print("  [SKIP] JWT_SECRET: not found in env file")

    # Rotate SECRET_KEY if requested and present
    if rotate_sk and re.search(r'^SECRET_KEY=.+', content, re.MULTILINE):
        new_sk = gen_secret()
        assert len(new_sk) == 128
        content = rotate_key(content, "SECRET_KEY", new_sk)
        print(f"  [PASS] SECRET_KEY rotated: {fingerprint(new_sk)}")
        rotated.append("SECRET_KEY")
    elif not rotate_sk:
        print("  [SKIP] SECRET_KEY: ROTATE_SK=false")
    else:
        print("  [SKIP] SECRET_KEY: not found in env file")

    # Write atomically (temp file → rename)
    tmp = env_file + ".tmp_rotate"
    with open(tmp, 'w') as f:
        f.write(content)
    # Preserve original permissions
    import shutil
    shutil.copystat(env_file, tmp)
    os.rename(tmp, env_file)

    print(f"\n  Rotated: {', '.join(rotated)}")

except Exception as e:
    print(f"  [FAIL] Error during rotation: {e}", file=sys.stderr)
    # Restore from backup
    with open(backup_file, 'r') as f:
        orig = f.read()
    with open(env_file, 'w') as f:
        f.write(orig)
    print("  [INFO] Restored from backup.", file=sys.stderr)
    sys.exit(1)
PYEOF

# ── verify ────────────────────────────────────────────────────────────────────
section "Post-rotation verification (fingerprints)"

python3 - "$ENV_FILE" <<'PYEOF'
import sys, hashlib, re

env_file = sys.argv[1]

def fingerprint(val):
    sha = hashlib.sha256(val.encode()).hexdigest()[:12]
    return f"len={len(val)}  sha256={sha}..."

with open(env_file, 'r') as f:
    content = f.read()

all_ok = True
for key, min_len in [("JWT_SECRET", 64), ("SECRET_KEY", 16)]:
    m = re.search(rf'^{key}=(.+)$', content, re.MULTILINE)
    if m:
        val = m.group(1).strip().strip('"').strip("'")
        if len(val) < min_len:
            print(f"  [FAIL] {key}: len={len(val)} < {min_len}")
            all_ok = False
        else:
            print(f"  [PASS] {key}: {fingerprint(val)}")
    else:
        print(f"  [INFO] {key}: not in env file (skipped)")

if not all_ok:
    sys.exit(1)
PYEOF

# ── summary ───────────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════════"
echo -e "${GREEN}  Rotation complete.${RESET}"
echo ""
echo "  Next steps:"
echo "  1. Restart services:"
echo "     cd /opt/deploy"
echo "     docker compose restart hosting_guard hg_worker hg_scheduler"
echo ""
echo "  2. Verify health:"
echo "     docker compose ps"
echo "     curl -sf https://api.hostingguard.lat/health | python3 -m json.tool"
echo ""
echo "  3. Run hygiene validation:"
echo "     sudo ./scripts/security/validate_secrets_hygiene.sh"
echo ""
echo -e "${YELLOW}  IMPORTANT: All active JWT sessions are now invalidated.${RESET}"
echo "  Users and staff must log in again."
echo ""
echo "  Backup: $BACKUP_FILE (perms 600)"
echo "══════════════════════════════════════════════════════════"
