#!/usr/bin/env bash
# validate_secrets_hygiene.sh  — P4E Secrets Hygiene Validation
#
# Validates credential hygiene for HostingGuard production:
#   - .env.production not world-readable
#   - docker-compose.yml not world-readable
#   - No real credentials hardcoded in docs/
#   - Critical variables exist, are non-empty, and have secure lengths
#   - No token patterns (sk-ant-, ghp_, ey...) in tracked files
#
# Usage:
#   sudo ./scripts/security/validate_secrets_hygiene.sh [--env-file /path/to/.env]
#   sudo ./scripts/security/validate_secrets_hygiene.sh --strict     (fail on WARN too)
#   sudo ./scripts/security/validate_secrets_hygiene.sh --self-test  (run .env format fixture tests)
#
# Environment overrides:
#   ENV_FILE      — default /opt/deploy/.env.production
#   COMPOSE_FILE  — default /opt/deploy/docker-compose.yml
#   DOCS_DIR      — root of checked-in docs (default: repo root)
#
# Exit codes:
#   0 — no failures (warnings may exist)
#   1 — one or more checks failed

set -euo pipefail

ENV_FILE="${ENV_FILE:-/opt/deploy/.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-/opt/deploy/docker-compose.yml}"
STRICT=false
SELF_TEST=false
PASS=0; WARN_COUNT=0; FAIL_COUNT=0

# Detect repo root (works both on server and dev machine)
REPO_ROOT="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel 2>/dev/null \
  || echo /opt/hosting_guard)"
DOCS_DIR="${DOCS_DIR:-$REPO_ROOT}"

# ── parse args ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)  ENV_FILE="$2"; shift 2 ;;
    --strict)    STRICT=true;   shift ;;
    --self-test) SELF_TEST=true; shift ;;
    *) echo "Unknown flag: $1"; exit 1 ;;
  esac
done

# ── colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RESET='\033[0m'
pass()  { echo -e "  ${GREEN}[PASS]${RESET} $*"; PASS=$((PASS+1)); }
fail()  { echo -e "  ${RED}[FAIL]${RESET} $*"; FAIL_COUNT=$((FAIL_COUNT+1)); }
warn()  { echo -e "  ${YELLOW}[WARN]${RESET} $*"; WARN_COUNT=$((WARN_COUNT+1)); }
info()  { echo -e "${CYAN}[INFO]${RESET} $*"; }
section(){ echo ""; echo -e "${YELLOW}── $* ──${RESET}"; }

# ── self-test ─────────────────────────────────────────────────────────────────
if [[ "$SELF_TEST" == "true" ]]; then
  echo ""
  echo "══════════════════════════════════════════════════════════"
  echo "  validate_secrets_hygiene.sh — .env format fixture self-test"
  echo "══════════════════════════════════════════════════════════"
  python3 <<'PYEOF'
import re, sys

def parse_value(content, key):
    m = re.search(
        rf'^\s*(?:export\s+)?{re.escape(key)}\s*=\s*([^\r\n]*)',
        content, re.MULTILINE
    )
    if not m:
        return None
    return m.group(1).strip().strip('"').strip("'")

KEYS = ["JWT_SECRET", "DATABASE_URL", "REDIS_URL"]

FIXTURES = [
    ("KEY=value",        "JWT_SECRET=x\nDATABASE_URL=postgres://x\nREDIS_URL=redis://x\n"),
    ("export KEY=value", "export JWT_SECRET=x\nexport DATABASE_URL=postgres://x\nexport REDIS_URL=redis://x\n"),
    ("leading spaces",   "  JWT_SECRET=x\n  DATABASE_URL=postgres://x\n  REDIS_URL=redis://x\n"),
    ("KEY = value",      "JWT_SECRET = x\nDATABASE_URL = postgres://x\nREDIS_URL = redis://x\n"),
    ("CRLF",             "JWT_SECRET=x\r\nDATABASE_URL=postgres://x\r\nREDIS_URL=redis://x\r\n"),
]

failures = 0
for desc, content in FIXTURES:
    missing = [k for k in KEYS if parse_value(content, k) is None]
    if missing:
        print(f"  [FAIL] {desc}: NOT FOUND: {missing}")
        failures += 1
    else:
        print(f"  [PASS] {desc}")

print()
if failures:
    print(f"  FAILED — {failures} fixture(s) failed.")
    sys.exit(1)
else:
    print("  All fixture tests passed.")
PYEOF
  exit $?
fi

echo ""
echo "══════════════════════════════════════════════════════════"
echo "  P4E — Secrets Hygiene Validation"
echo "  Env file:   $ENV_FILE"
echo "  Compose:    $COMPOSE_FILE"
echo "  Docs root:  $DOCS_DIR"
echo "══════════════════════════════════════════════════════════"

# ─── 1. File permissions ──────────────────────────────────────────────────────
section "File permissions"

check_not_world_readable() {
  local file="$1" label="$2"
  if [[ ! -f "$file" ]]; then
    warn "$label not found at $file (skipping permission check)"
    return
  fi
  local perms world_bit
  perms=$(stat -c "%a" "$file" 2>/dev/null || stat -f "%OLp" "$file" 2>/dev/null || echo "000")
  world_bit="${perms: -1}"
  if [[ "$world_bit" != "0" ]]; then
    fail "$label is world-readable (perms=$perms) — fix: chmod o-r \"$file\""
  else
    pass "$label permissions: $perms (not world-readable)"
  fi
}

check_not_world_readable "$ENV_FILE"      ".env.production"
check_not_world_readable "$COMPOSE_FILE"  "docker-compose.yml"

# ─── 2. Critical variables exist and are non-empty ────────────────────────────
section "Critical variables — existence and length"

if [[ ! -f "$ENV_FILE" ]]; then
  fail "Env file not found: $ENV_FILE — skipping variable checks"
else
  python3 - "$ENV_FILE" <<'PYEOF'
import sys, re, hashlib

env_file = sys.argv[1]

CHECKS = [
    # (key, min_length, required)
    ("JWT_SECRET",         32, True),
    ("SECRET_KEY",         16, False),
    ("DATABASE_URL",        8, True),
    ("REDIS_URL",           8, True),
]

with open(env_file, 'r') as f:
    content = f.read()

failures = 0
for key, min_len, required in CHECKS:
    m = re.search(
        rf'^\s*(?:export\s+)?{re.escape(key)}\s*=\s*([^\r\n]*)',
        content, re.MULTILINE
    )
    if not m:
        if required:
            print(f"  [FAIL] {key}: not found in env file")
            failures += 1
        else:
            print(f"  [INFO] {key}: not set (optional)")
        continue

    val = m.group(1).strip().strip('"').strip("'")
    if not val:
        print(f"  [FAIL] {key}: empty")
        failures += 1
        continue

    sha = hashlib.sha256(val.encode()).hexdigest()[:8]
    if len(val) < min_len:
        print(f"  [FAIL] {key}: len={len(val)} < {min_len} (too short) sha256={sha}...")
        failures += 1
    else:
        print(f"  [PASS] {key}: len={len(val)} sha256={sha}... (>= {min_len})")

if failures:
    sys.exit(1)
PYEOF
fi

# ─── 3. No credentials in docs / tracked files ───────────────────────────────
section "Credential leak scan (docs and tracked files)"

# Patterns that indicate real credentials were committed
_scan_credential_patterns() {
  local dir="$1"
  local found=0

  # Anthropic API key
  if grep -rn --include="*.md" --include="*.yml" --include="*.yaml" --include="*.txt" \
       -E "sk-ant-[a-zA-Z0-9_-]{20,}" "$dir" 2>/dev/null; then
    fail "Anthropic API key pattern (sk-ant-...) found in docs"
    found=1
  fi

  # GitHub tokens
  if grep -rn --include="*.md" --include="*.yml" --include="*.yaml" \
       -E "ghp_[a-zA-Z0-9]{36}|gho_[a-zA-Z0-9]{36}" "$dir" 2>/dev/null; then
    fail "GitHub token pattern (ghp_/gho_) found in docs"
    found=1
  fi

  # Redis URL with password
  if grep -rn --include="*.md" --include="*.yml" --include="*.yaml" \
       -E "redis://:[^@]+@[^/]" "$dir" 2>/dev/null; then
    fail "Redis URL with credentials found in docs"
    found=1
  fi

  # PostgreSQL URL with password
  if grep -rn --include="*.md" --include="*.yml" --include="*.yaml" \
       -E "postgresql://[^:]+:[^@]+@" "$dir" 2>/dev/null | \
     grep -v "REDACTED\|example\|placeholder\|<" 2>/dev/null; then
    fail "PostgreSQL URL with credentials found in docs"
    found=1
  fi

  # Bearer tokens / raw JWTs (base64url encoded, 3 parts)
  if grep -rn --include="*.md" \
       -E "Bearer ey[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}" \
       "$dir" 2>/dev/null; then
    fail "Raw JWT Bearer token found in docs"
    found=1
  fi

  # LemonSqueezy keys
  if grep -rn --include="*.md" --include="*.yml" \
       -E "ls_[a-z]+_[a-zA-Z0-9]{40,}" "$dir" 2>/dev/null; then
    fail "LemonSqueezy API key pattern found in docs"
    found=1
  fi

  return $found
}

if _scan_credential_patterns "$DOCS_DIR/docs" 2>/dev/null; then
  pass "No credential patterns found in docs/"
fi

# DATABASE_URL real value check (docs should use [REDACTED] or placeholders)
section "DATABASE_URL and REDIS_URL in docs"

if grep -rn --include="*.md" \
     -E "DATABASE_URL=postgresql://[^:]+:[^@]{4,}@" \
     "$DOCS_DIR/docs" 2>/dev/null | grep -v "REDACTED\|example\|<"; then
  fail "Real DATABASE_URL found in docs — redact with [REDACTED]"
else
  pass "No real DATABASE_URL in docs"
fi

if grep -rn --include="*.md" \
     -E "REDIS_URL=redis://:[^@]{4,}@" \
     "$DOCS_DIR/docs" 2>/dev/null | grep -v "REDACTED\|example\|<"; then
  fail "Real REDIS_URL with password found in docs"
else
  pass "No real REDIS_URL with password in docs"
fi

# ─── 4. No plaintext secrets in docker-compose.yml ───────────────────────────
section "docker-compose.yml secret references"

if [[ -f "$COMPOSE_FILE" ]]; then
  # Compose should reference ${VAR} not raw values for secrets
  python3 - "$COMPOSE_FILE" <<'PYEOF'
import sys, re

compose_file = sys.argv[1]
with open(compose_file, 'r') as f:
    content = f.read()

secret_keys = ["JWT_SECRET", "SECRET_KEY", "DATABASE_URL", "REDIS_URL",
               "POSTGRES_PASSWORD", "SMTP_PASS", "CLAUDE_API_KEY"]

issues = 0
for key in secret_keys:
    # Look for KEY: <value> where value is not ${...} or empty
    m = re.search(rf'{key}:\s+([^$\n{{}}].+)', content)
    if m:
        val = m.group(1).strip()
        if not val.startswith("$") and not val.startswith("#") and len(val) > 2:
            print(f"  [WARN] {key} appears hardcoded in compose: (value hidden)")
            issues += 1
        else:
            print(f"  [PASS] {key} uses variable reference")
    else:
        # Check env_file format: KEY=value (for env_file block)
        m2 = re.search(rf'^    {key}=([^$\n].+)', content, re.MULTILINE)
        if m2:
            # env_file entries that are not ${VAR} refs
            print(f"  [INFO] {key} found in env_file block")

if issues == 0:
    print("  [PASS] No hardcoded secrets detected in docker-compose.yml")
PYEOF
else
  warn "docker-compose.yml not found at $COMPOSE_FILE — skipping compose check"
fi

# ─── 5. Backup check ─────────────────────────────────────────────────────────
section "Backup files (permissions)"

backup_count=0
while IFS= read -r -d '' backup; do
  backup_count=$((backup_count + 1))
  perms=$(stat -c "%a" "$backup" 2>/dev/null || stat -f "%OLp" "$backup" 2>/dev/null || echo "000")
  owner_digit="${perms:0:1}"
  group_digit="${perms:1:1}"
  world_digit="${perms:2:1}"
  if (( world_digit != 0 )); then
    fail "Backup $backup is world-readable (perms=$perms)"
  elif (( group_digit & 2 )); then
    warn "Backup $backup is group-writable (perms=$perms)"
  else
    pass "Backup $backup: perms=$perms (OK)"
  fi
done < <(
  {
    find /root -maxdepth 1 -type f -name ".env.production.backup*" -print0 2>/dev/null || true
    find /opt/backups -maxdepth 1 -type f -name ".env*" -print0 2>/dev/null || true
  }
)

if [[ "$backup_count" -eq 0 ]]; then
  info "No backup files found to validate"
fi

# ─── summary ─────────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════════"
echo "  Results: $PASS passed, $WARN_COUNT warnings, $FAIL_COUNT failures"
echo "══════════════════════════════════════════════════════════"

if [[ $FAIL_COUNT -gt 0 ]]; then
  echo -e "${RED}  FAIL — $FAIL_COUNT hygiene check(s) failed.${RESET}"
  exit 1
elif [[ $WARN_COUNT -gt 0 && "$STRICT" == "true" ]]; then
  echo -e "${YELLOW}  WARN — $WARN_COUNT warning(s) in strict mode.${RESET}"
  exit 1
elif [[ $WARN_COUNT -gt 0 ]]; then
  echo -e "${YELLOW}  WARN — $WARN_COUNT warning(s). Run with --strict to fail on warnings.${RESET}"
  exit 0
else
  echo -e "${GREEN}  SECURE — All hygiene checks passed.${RESET}"
  exit 0
fi
