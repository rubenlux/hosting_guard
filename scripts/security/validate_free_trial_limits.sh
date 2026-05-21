#!/usr/bin/env bash
# validate_free_trial_limits.sh
# Verify that free-trial limits and AI quota guards are correctly wired in code.
# Run from repo root: bash scripts/security/validate_free_trial_limits.sh

set -euo pipefail
PASS=0
FAIL=0

ok()   { echo "  [OK]  $1"; ((PASS++)) || true; }
fail() { echo "  [FAIL] $1"; ((FAIL++)) || true; }

echo ""
echo "=== Free Trial & AI Quota — Code Validation ==="
echo ""

# ── 1. PLANS dict ────────────────────────────────────────────────────────────
echo "1. PLANS dict (hosting.py)"

grep -q '"free".*"days".*14\|"days".*14.*"free"' app/api/routes/hosting.py \
  && ok "free plan days=14 present" \
  || fail "free plan days=14 NOT found in hosting.py"

grep -q 'MAX_FREE_USERS\s*=\s*10' app/api/routes/hosting.py \
  && ok "MAX_FREE_USERS=10 present" \
  || fail "MAX_FREE_USERS=10 NOT found"

# ── 2. Expiration job ────────────────────────────────────────────────────────
echo ""
echo "2. Expiration job (expiration_job.py)"

grep -q 'FREE_PLAN_DAYS\s*=\s*14' app/services/expiration_job.py \
  && ok "FREE_PLAN_DAYS=14 present" \
  || fail "FREE_PLAN_DAYS=14 NOT found in expiration_job.py"

grep -q 'check_and_expire_free_hostings' app/services/expiration_job.py \
  && ok "check_and_expire_free_hostings function present" \
  || fail "check_and_expire_free_hostings NOT found"

# ── 3. AI quota service ──────────────────────────────────────────────────────
echo ""
echo "3. AI quota service (ai_quota_service.py)"

grep -q '_FREE_TRIAL_TOTAL\s*=\s*10' app/services/ai_quota_service.py \
  && ok "_FREE_TRIAL_TOTAL=10 present" \
  || fail "_FREE_TRIAL_TOTAL=10 NOT found"

grep -q '_FREE_DAILY_LIMIT\s*=\s*3' app/services/ai_quota_service.py \
  && ok "_FREE_DAILY_LIMIT=3 present" \
  || fail "_FREE_DAILY_LIMIT=3 NOT found"

grep -q 'def check_ai_quota' app/services/ai_quota_service.py \
  && ok "check_ai_quota function present" \
  || fail "check_ai_quota NOT found"

grep -q 'def record_ai_usage' app/services/ai_quota_service.py \
  && ok "record_ai_usage function present" \
  || fail "record_ai_usage NOT found"

grep -q 'plan_economics' app/services/ai_quota_service.py \
  && ok "quota service reads plan_economics table" \
  || fail "plan_economics NOT referenced in quota service"

# ── 4. DB migration ──────────────────────────────────────────────────────────
echo ""
echo "4. DB migration (migrations.py)"

grep -q 'ai_usage_events' app/infra/migrations.py \
  && ok "ai_usage_events table in migrations.py" \
  || fail "ai_usage_events NOT in migrations.py"

grep -q 'idx_ai_usage_user_feature' app/infra/migrations.py \
  && ok "idx_ai_usage_user_feature index present" \
  || fail "idx_ai_usage_user_feature index NOT found"

# ── 5. Support chat integration ──────────────────────────────────────────────
echo ""
echo "5. Quota guard integration (support_chat.py)"

grep -q 'check_ai_quota' app/api/routes/support_chat.py \
  && ok "check_ai_quota called in support_chat.py" \
  || fail "check_ai_quota NOT found in support_chat.py"

grep -q 'record_ai_usage' app/api/routes/support_chat.py \
  && ok "record_ai_usage called in support_chat.py" \
  || fail "record_ai_usage NOT found in support_chat.py"

# Verify guard appears BEFORE generate_support_response in create_ticket
# Skip import lines (lines that start with 'from' or 'import')
CHECK_LINE=$(grep -n 'check_ai_quota' app/api/routes/support_chat.py \
  | grep -v '^\s*#\|^[0-9]*:from \|^[0-9]*:import ' | head -1 | cut -d: -f1)
GENERATE_LINE=$(grep -n 'await generate_support_response' app/api/routes/support_chat.py \
  | head -1 | cut -d: -f1)

if [[ -n "$CHECK_LINE" && -n "$GENERATE_LINE" && "$CHECK_LINE" -lt "$GENERATE_LINE" ]]; then
  ok "check_ai_quota (line $CHECK_LINE) is before generate_support_response (line $GENERATE_LINE)"
else
  fail "check_ai_quota must appear before generate_support_response in create_ticket"
fi

# ── 6. Admin endpoint ────────────────────────────────────────────────────────
echo ""
echo "6. Admin AI usage endpoint (admin.py)"

grep -q '"/ai-usage"' app/api/routes/admin.py \
  && ok "/admin/ai-usage endpoint present" \
  || fail "/admin/ai-usage NOT found in admin.py"

grep -q 'get_ai_usage_summary' app/api/routes/admin.py \
  && ok "get_ai_usage_summary wired in admin.py" \
  || fail "get_ai_usage_summary NOT wired"

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "================================================="
echo "Results: $PASS passed, $FAIL failed"
echo "================================================="
echo ""

if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
