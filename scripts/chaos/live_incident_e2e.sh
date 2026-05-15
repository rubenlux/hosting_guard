#!/usr/bin/env bash
# ============================================================
# HostingGuard — Live Incident E2E Chaos Test
# ============================================================
# Tests that a real incident on a disposable tenant:
#   1. Gets detected by Router Health Guard
#   2. Is enriched with matched_runbook_id
#   3. Causes dashboard health score to drop
#   4. Can be repaired safely
#
# Usage:
#   CHAOS_ACCEPT_RISK=true bash scripts/chaos/live_incident_e2e.sh \
#     --tenant-id 42 \
#     --tenant-container hg_site_42 \
#     --domain test-chaos.hostingguard.lat \
#     --case welcome_to_nginx \
#     --token <admin_bearer_token>
#
# Dry-run (no container changes):
#   CHAOS_ACCEPT_RISK=true bash scripts/chaos/live_incident_e2e.sh \
#     --tenant-id 42 --tenant-container hg_site_42 \
#     --domain test-chaos.hostingguard.lat \
#     --case welcome_to_nginx --token <token> --dry-run
# ============================================================
set -euo pipefail

# ─── Timestamp & paths ────────────────────────────────────────────────────────
TS=$(date +%Y%m%d_%H%M%S)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPORT_DIR="${REPO_ROOT}/chaos_reports"
REPORT_MD="${REPORT_DIR}/live_e2e_${TS}.md"
REPORT_JSON="${REPORT_DIR}/live_e2e_${TS}.json"

# ─── Defaults ─────────────────────────────────────────────────────────────────
TENANT_ID=""
TENANT_CONTAINER=""
DOMAIN=""
CASE=""
API_BASE="http://localhost:8000"
TOKEN=""
DRY_RUN=false

# ─── Parse arguments ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tenant-id)        TENANT_ID="$2";        shift 2 ;;
    --tenant-container) TENANT_CONTAINER="$2"; shift 2 ;;
    --domain)           DOMAIN="$2";           shift 2 ;;
    --case)             CASE="$2";             shift 2 ;;
    --api)              API_BASE="$2";         shift 2 ;;
    --token)            TOKEN="$2";            shift 2 ;;
    --dry-run)          DRY_RUN=true;          shift   ;;
    *)
      echo "[E2E] Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

# ─── State tracking (for cleanup and report) ─────────────────────────────────
CONTAINER_MODIFIED=false
CHAOS_CONTAINER_STARTED=false
ORIGINAL_CONTAINER_BAK=""
STEP_LOG=()           # array of "PASS|FAIL: description"
FINAL_STATE="UNKNOWN"
REPAIR_SUCCESSFUL=false
CURL_STATUS_AFTER_REPAIR=""
INCIDENT_DETECTED=false
INCIDENT_TYPE=""
MATCHED_RUNBOOK_ID=""
SAFE_ACTIONS="[]"
FORBIDDEN_ACTIONS="[]"
DASHBOARD_SCORE_DURING_INCIDENT="null"
CURL_STATUS_BROKEN=""
ERROR_DETAILS=""

# ─── Helpers ─────────────────────────────────────────────────────────────────
log()  { echo "[E2E $(date +%H:%M:%S)] $*"; }
pass() { local msg="$*"; log "PASS: ${msg}"; STEP_LOG+=("PASS: ${msg}"); }
fail() { local msg="$*"; log "FAIL: ${msg}"; STEP_LOG+=("FAIL: ${msg}"); ERROR_DETAILS="${msg}"; }
warn() { local msg="$*"; log "WARN: ${msg}"; STEP_LOG+=("WARN: ${msg}"); }
step() { log "--- STEP: $* ---"; }

# curl with consistent flags.
# The API uses cookie-based JWT auth (access_token cookie), NOT Bearer tokens.
# --TOKEN is the raw JWT value; it is sent as the access_token cookie.
api_get() {
  local path="$1"
  curl --max-time 10 --silent \
    -b "access_token=${TOKEN}" \
    "${API_BASE}${path}"
}

api_get_status() {
  # Like api_get but also returns the HTTP status code on stderr for debug
  local path="$1"
  curl --max-time 10 --silent --write-out "\nHTTP_STATUS:%{http_code}" \
    -b "access_token=${TOKEN}" \
    "${API_BASE}${path}"
}

api_post() {
  local path="$1"
  local body="$2"
  curl --max-time 10 --silent \
    -X POST \
    -b "access_token=${TOKEN}" \
    -H "Content-Type: application/json" \
    -d "${body}" \
    "${API_BASE}${path}"
}

# Emit final report files (always called, even on error)
emit_report() {
  local exit_code="${1:-0}"
  mkdir -p "${REPORT_DIR}"

  # Build steps JSON array
  local steps_json="["
  local first=true
  for entry in "${STEP_LOG[@]:-}"; do
    if [[ "${first}" == "true" ]]; then first=false; else steps_json+=","; fi
    local status result_text
    if [[ "${entry}" == PASS:* ]]; then
      status="pass"; result_text="${entry#PASS: }"
    elif [[ "${entry}" == WARN:* ]]; then
      status="warn"; result_text="${entry#WARN: }"
    else
      status="fail"; result_text="${entry#FAIL: }"
    fi
    # Escape double-quotes for JSON
    result_text="${result_text//\"/\\\"}"
    steps_json+="{\"status\":\"${status}\",\"description\":\"${result_text}\"}"
  done
  steps_json+="]"

  # Determine overall pass/fail — WARN entries are non-fatal
  local overall="PASSED"
  for entry in "${STEP_LOG[@]:-}"; do
    if [[ "${entry}" == FAIL:* ]]; then overall="FAILED"; break; fi
  done
  [[ "${exit_code}" -ne 0 ]] && overall="FAILED"

  # ── JSON report ──────────────────────────────────────────────────────────────
  cat > "${REPORT_JSON}" <<JSON
{
  "report_version": "1",
  "generated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "case": "${CASE}",
  "tenant_id": ${TENANT_ID:-null},
  "domain": "${DOMAIN}",
  "tenant_container": "${TENANT_CONTAINER}",
  "dry_run": ${DRY_RUN},
  "overall": "${overall}",
  "incident_detected": ${INCIDENT_DETECTED},
  "incident_type": $(json_string_or_null "${INCIDENT_TYPE}"),
  "matched_runbook_id": $(json_string_or_null "${MATCHED_RUNBOOK_ID}"),
  "safe_actions": ${SAFE_ACTIONS},
  "forbidden_actions": ${FORBIDDEN_ACTIONS},
  "dashboard_score_during_incident": ${DASHBOARD_SCORE_DURING_INCIDENT},
  "repair_successful": ${REPAIR_SUCCESSFUL},
  "curl_status_after_repair": $(json_string_or_null "${CURL_STATUS_AFTER_REPAIR}"),
  "curl_status_broken": $(json_string_or_null "${CURL_STATUS_BROKEN}"),
  "error_details": $(json_string_or_null "${ERROR_DETAILS}"),
  "steps": ${steps_json}
}
JSON

  # ── Markdown report ──────────────────────────────────────────────────────────
  {
    echo "# HostingGuard Live Incident E2E — ${overall}"
    echo ""
    echo "| Field | Value |"
    echo "|-------|-------|"
    echo "| Date | $(date -u +%Y-%m-%dT%H:%M:%SZ) |"
    echo "| Case | \`${CASE}\` |"
    echo "| Tenant ID | ${TENANT_ID} |"
    echo "| Domain | ${DOMAIN} |"
    echo "| Container | \`${TENANT_CONTAINER}\` |"
    echo "| API | ${API_BASE} |"
    echo "| Dry-run | ${DRY_RUN} |"
    echo ""
    echo "## Result: ${overall}"
    echo ""
    echo "| Metric | Value |"
    echo "|--------|-------|"
    echo "| Incident detected | ${INCIDENT_DETECTED} |"
    echo "| Incident type | ${INCIDENT_TYPE:-n/a} |"
    echo "| Matched runbook | ${MATCHED_RUNBOOK_ID:-n/a} |"
    echo "| Dashboard score during incident | ${DASHBOARD_SCORE_DURING_INCIDENT} |"
    echo "| Repair successful | ${REPAIR_SUCCESSFUL} |"
    echo "| curl status after repair | ${CURL_STATUS_AFTER_REPAIR:-n/a} |"
    echo "| curl status when broken | ${CURL_STATUS_BROKEN:-n/a} |"
    echo ""
    echo "### Safe actions"
    echo "\`\`\`json"
    echo "${SAFE_ACTIONS}"
    echo "\`\`\`"
    echo ""
    echo "### Forbidden actions"
    echo "\`\`\`json"
    echo "${FORBIDDEN_ACTIONS}"
    echo "\`\`\`"
    echo ""
    echo "## Steps"
    echo ""
    for entry in "${STEP_LOG[@]:-}"; do
      if [[ "${entry}" == PASS:* ]]; then
        echo "- [x] ${entry#PASS: }"
      elif [[ "${entry}" == WARN:* ]]; then
        echo "- [~] **WARN** ${entry#WARN: }"
      else
        echo "- [ ] **FAIL** ${entry#FAIL: }"
      fi
    done
    if [[ -n "${ERROR_DETAILS}" ]]; then
      echo ""
      echo "## Error Details"
      echo ""
      echo "\`\`\`"
      echo "${ERROR_DETAILS}"
      echo "\`\`\`"
    fi
  } > "${REPORT_MD}"

  log "Report (MD):   ${REPORT_MD}"
  log "Report (JSON): ${REPORT_JSON}"
}

# Emit null for empty strings in JSON
json_string_or_null() {
  local val="$1"
  if [[ -z "${val}" ]]; then
    echo "null"
  else
    val="${val//\\/\\\\}"
    val="${val//\"/\\\"}"
    echo "\"${val}\""
  fi
}

# ─── Cleanup function (called on EXIT / SIGINT / SIGTERM) ────────────────────
cleanup() {
  local exit_code=$?
  # Prevent re-entrancy
  trap - EXIT SIGINT SIGTERM

  log "Running cleanup..."

  if [[ "${CONTAINER_MODIFIED}" == "true" && "${DRY_RUN}" == "false" ]]; then
    log "Restoring tenant container state..."

    # Stop the chaos container if it is running
    if [[ "${CHAOS_CONTAINER_STARTED}" == "true" ]]; then
      docker stop "${TENANT_CONTAINER}" 2>/dev/null && log "Stopped chaos container ${TENANT_CONTAINER}" || true
      docker rm "${TENANT_CONTAINER}" 2>/dev/null && log "Removed chaos container ${TENANT_CONTAINER}" || true
    fi

    # Restore from backup rename
    if [[ -n "${ORIGINAL_CONTAINER_BAK}" ]]; then
      if docker inspect "${ORIGINAL_CONTAINER_BAK}" &>/dev/null; then
        docker rename "${ORIGINAL_CONTAINER_BAK}" "${TENANT_CONTAINER}" 2>/dev/null \
          && log "Renamed ${ORIGINAL_CONTAINER_BAK} back to ${TENANT_CONTAINER}" \
          || log "WARNING: could not rename backup container back"
        docker start "${TENANT_CONTAINER}" 2>/dev/null \
          && log "Started restored container ${TENANT_CONTAINER}" \
          || log "WARNING: could not start restored container"
      else
        log "WARNING: backup container ${ORIGINAL_CONTAINER_BAK} not found — manual restore required"
      fi
    fi
  else
    log "No container modifications to undo (dry_run=${DRY_RUN}, modified=${CONTAINER_MODIFIED})"
  fi

  emit_report "${exit_code}"
  exit "${exit_code}"
}

trap cleanup EXIT SIGINT SIGTERM

# ─── Safety Gate 1: CHAOS_ACCEPT_RISK ────────────────────────────────────────
if [[ "${CHAOS_ACCEPT_RISK:-}" != "true" ]]; then
  echo "[E2E] SAFETY GATE FAILED: CHAOS_ACCEPT_RISK env var must be set to 'true'." >&2
  echo "[E2E] This script modifies live Docker containers and may cause brief downtime." >&2
  echo "[E2E] Run: CHAOS_ACCEPT_RISK=true bash $0 ..." >&2
  exit 1
fi

# ─── Safety Gate 2: --tenant-id required ─────────────────────────────────────
if [[ -z "${TENANT_ID}" ]]; then
  echo "[E2E] SAFETY GATE FAILED: --tenant-id is required." >&2
  exit 1
fi

# ─── Safety Gate 3: --case must be valid ─────────────────────────────────────
VALID_CASES=("welcome_to_nginx" "empty_mounts" "delete_route")
CASE_VALID=false
for vc in "${VALID_CASES[@]}"; do
  [[ "${CASE}" == "${vc}" ]] && CASE_VALID=true && break
done
if [[ "${CASE_VALID}" == "false" ]]; then
  echo "[E2E] SAFETY GATE FAILED: --case must be one of: ${VALID_CASES[*]}" >&2
  echo "[E2E] Got: '${CASE}'" >&2
  exit 1
fi

# ─── Safety Gate 4 & 5: validate disposable tenant via API ───────────────────
log "Validating tenant ${TENANT_ID} is disposable..."

if [[ -z "${TOKEN}" ]]; then
  echo "[E2E] SAFETY GATE FAILED: --token is required to validate tenant." >&2
  exit 1
fi

# Strategy 1: direct single-tenant endpoint (added in P0.2)
log "Trying direct tenant lookup: GET /admin/hostings/${TENANT_ID} ..."
DIRECT_RESPONSE=$(api_get_status "/admin/hostings/${TENANT_ID}" 2>/dev/null || echo "")

# Extract HTTP status from response
DIRECT_HTTP_STATUS=$(echo "${DIRECT_RESPONSE}" | grep -o 'HTTP_STATUS:[0-9]*' | cut -d: -f2 || echo "0")
DIRECT_BODY=$(echo "${DIRECT_RESPONSE}" | sed '/HTTP_STATUS:/d')

log "Direct lookup HTTP status: ${DIRECT_HTTP_STATUS}"

if [[ "${DIRECT_HTTP_STATUS}" == "200" ]]; then
  TENANT_JSON="${DIRECT_BODY}"
  log "Tenant found via direct endpoint."
elif [[ "${DIRECT_HTTP_STATUS}" == "401" || "${DIRECT_HTTP_STATUS}" == "422" ]]; then
  echo "[E2E] SAFETY GATE FAILED: Auth error (HTTP ${DIRECT_HTTP_STATUS}) — is --token a valid admin JWT?" >&2
  echo "[E2E] The API uses cookie auth. --token must be the raw JWT value of the access_token cookie." >&2
  echo "[E2E] Extract it from browser: DevTools → Application → Cookies → access_token → Copy Value" >&2
  exit 1
elif [[ "${DIRECT_HTTP_STATUS}" == "403" ]]; then
  echo "[E2E] SAFETY GATE FAILED: Forbidden (HTTP 403) — token valid but not admin role." >&2
  exit 1
else
  # Strategy 2: fallback to list endpoint
  log "Direct endpoint returned HTTP ${DIRECT_HTTP_STATUS}. Falling back to list endpoint..."
  LIST_RESPONSE=$(api_get_status "/admin/hostings?limit=1000" 2>/dev/null || echo "")
  LIST_HTTP_STATUS=$(echo "${LIST_RESPONSE}" | grep -o 'HTTP_STATUS:[0-9]*' | cut -d: -f2 || echo "0")
  LIST_BODY=$(echo "${LIST_RESPONSE}" | sed '/HTTP_STATUS:/d')

  log "List endpoint HTTP status: ${LIST_HTTP_STATUS}"

  if [[ "${LIST_HTTP_STATUS}" == "401" || "${LIST_HTTP_STATUS}" == "422" ]]; then
    echo "[E2E] SAFETY GATE FAILED: Auth error (HTTP ${LIST_HTTP_STATUS}) — is --token a valid admin JWT?" >&2
    echo "[E2E] Token format: raw JWT value of access_token cookie, NOT Bearer prefix." >&2
    exit 1
  fi

  if [[ -z "${LIST_BODY}" || "${LIST_HTTP_STATUS}" != "200" ]]; then
    echo "[E2E] SAFETY GATE FAILED: Could not reach ${API_BASE}/admin/hostings (HTTP ${LIST_HTTP_STATUS:-timeout})" >&2
    exit 1
  fi

  # Log response shape for debugging
  ITEM_COUNT=$(echo "${LIST_BODY}" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if isinstance(data, list): print(len(data))
elif isinstance(data, dict): print(len(data.get('hostings', data.get('results', []))))
else: print(0)
" 2>/dev/null || echo "?")
  log "List response: ${ITEM_COUNT} hostings found."

  TENANT_JSON=$(echo "${LIST_BODY}" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if isinstance(data, list):
    hostings = data
elif isinstance(data, dict):
    hostings = data.get('hostings', data.get('results', data.get('items', [])))
else:
    hostings = []
tid = int('${TENANT_ID}')
for h in hostings:
    if int(h.get('hosting_id', -1)) == tid:
        print(json.dumps(h))
        sys.exit(0)
# Log all IDs for debugging
ids = [h.get('hosting_id') for h in hostings[:20]]
print('null', file=sys.stderr)
print(f'Available IDs (first 20): {ids}', file=sys.stderr)
" 2>/tmp/e2e_debug.txt || echo "null")

  if [[ "${TENANT_JSON}" == "null" || -z "${TENANT_JSON}" ]]; then
    echo "[E2E] SAFETY GATE FAILED: Tenant ${TENANT_ID} not found." >&2
    echo "[E2E] Debug info:" >&2
    cat /tmp/e2e_debug.txt 2>/dev/null >&2 || true
    echo "[E2E] Check that hosting_id=${TENANT_ID} exists and status != 'deleted'." >&2
    exit 1
  fi
fi

# Extract plan and subdomain from the tenant record
TENANT_PLAN=$(echo "${TENANT_JSON}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('plan','unknown'))" 2>/dev/null || echo "unknown")
TENANT_SUBDOMAIN=$(echo "${TENANT_JSON}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('subdomain','') or d.get('domain',''))" 2>/dev/null || echo "")

log "Tenant plan: ${TENANT_PLAN}, subdomain: ${TENANT_SUBDOMAIN}"

# Check if domain contains safe keywords
DOMAIN_LOWER="${DOMAIN,,}"
SUBDOMAIN_LOWER="${TENANT_SUBDOMAIN,,}"
IS_SAFE_DOMAIN=false

for keyword in "chaos" "test" "staging"; do
  if [[ "${DOMAIN_LOWER}" == *"${keyword}"* ]] || [[ "${SUBDOMAIN_LOWER}" == *"${keyword}"* ]]; then
    IS_SAFE_DOMAIN=true
    break
  fi
done

if [[ "${TENANT_PLAN}" == "free" ]]; then
  IS_SAFE_DOMAIN=true
fi

if [[ "${IS_SAFE_DOMAIN}" == "false" ]]; then
  echo "[E2E] SAFETY GATE FAILED: Tenant ${TENANT_ID} does not appear to be a disposable tenant." >&2
  echo "[E2E] Plan='${TENANT_PLAN}', domain='${DOMAIN}', subdomain='${TENANT_SUBDOMAIN}'" >&2
  echo "[E2E] Disposable tenants must have: plan='free' OR domain containing 'chaos/test/staging'." >&2
  echo "[E2E] Refusing to run chaos test on a potential production tenant." >&2
  exit 1
fi

log "Safety gates passed. Tenant ${TENANT_ID} is disposable (plan=${TENANT_PLAN})."

# ─── Additional required args ─────────────────────────────────────────────────
if [[ -z "${TENANT_CONTAINER}" ]]; then
  echo "[E2E] ERROR: --tenant-container is required." >&2
  exit 1
fi

if [[ -z "${DOMAIN}" ]]; then
  echo "[E2E] ERROR: --domain is required." >&2
  exit 1
fi

# ─── Main test body ───────────────────────────────────────────────────────────
log "Starting E2E chaos test: case=${CASE}, tenant=${TENANT_ID}, container=${TENANT_CONTAINER}"
log "Domain: ${DOMAIN}"
log "API: ${API_BASE}"
log "Dry-run: ${DRY_RUN}"
echo ""

# ─── CASE: welcome_to_nginx ───────────────────────────────────────────────────
run_welcome_to_nginx() {
  step "1/7  Save original container state"
  ORIGINAL_IMAGE=$(docker inspect --format='{{.Config.Image}}' "${TENANT_CONTAINER}" 2>/dev/null || echo "")
  if [[ -z "${ORIGINAL_IMAGE}" ]]; then
    fail "Could not inspect container '${TENANT_CONTAINER}' — is it running?"
    return 1
  fi
  log "Original image: ${ORIGINAL_IMAGE}"
  pass "Container '${TENANT_CONTAINER}' inspected, image=${ORIGINAL_IMAGE}"

  if [[ "${DRY_RUN}" == "true" ]]; then
    log "[DRY-RUN] Would inject nginx default page. Skipping container changes."
    step "DRY-RUN: Verifying detection path (no container changes)"
    MATCH_RESP=$(api_post "/admin/knowledge/match" '{"text":"Welcome to nginx!"}')
    MATCHED_RUNBOOK_ID=$(echo "${MATCH_RESP}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
rb = d.get('matched_runbook', d.get('runbook', {})) or {}
print(rb.get('incident_id', d.get('matched_runbook_id', '')))" 2>/dev/null || echo "")
    if [[ -n "${MATCHED_RUNBOOK_ID}" ]]; then
      INCIDENT_DETECTED=true
      pass "DRY-RUN: knowledge/match returned matched_runbook_id=${MATCHED_RUNBOOK_ID}"
      SAFE_ACTIONS=$(echo "${MATCH_RESP}" | python3 -c "import sys,json; d=json.load(sys.stdin); rb=d.get('matched_runbook',d.get('runbook',{})) or {}; print(json.dumps(rb.get('safe_actions',[])))" 2>/dev/null || echo "[]")
      FORBIDDEN_ACTIONS=$(echo "${MATCH_RESP}" | python3 -c "import sys,json; d=json.load(sys.stdin); rb=d.get('matched_runbook',d.get('runbook',{})) or {}; print(json.dumps(rb.get('forbidden_actions',[])))" 2>/dev/null || echo "[]")
    else
      fail "DRY-RUN: knowledge/match returned no runbook for 'Welcome to nginx!' text"
    fi
    REPAIR_SUCCESSFUL=true
    FINAL_STATE="DRY_RUN_COMPLETE"
    return 0
  fi

  # ── Step 2: inject failure ───────────────────────────────────────────────────
  step "2/7  Inject failure: replace container with nginx:alpine"
  BAK_NAME="${TENANT_CONTAINER}_bak_$(date +%s)"
  ORIGINAL_CONTAINER_BAK="${BAK_NAME}"

  docker stop "${TENANT_CONTAINER}"
  log "Stopped ${TENANT_CONTAINER}"

  docker rename "${TENANT_CONTAINER}" "${BAK_NAME}"
  log "Renamed to ${BAK_NAME}"

  docker run -d --name "${TENANT_CONTAINER}" nginx:alpine
  CHAOS_CONTAINER_STARTED=true
  CONTAINER_MODIFIED=true
  log "Started chaos container ${TENANT_CONTAINER} (nginx:alpine)"
  pass "Chaos container deployed"

  # Short propagation wait
  sleep 3

  # ── Step 3: public curl check (informational) ────────────────────────────────
  # Cloudflare may return 301/redirect/cached page instead of the origin body.
  # This step is non-fatal: API-level detection (steps 4-6) is the authoritative signal.
  step "3/7  Public curl check (informational — Cloudflare may intercept)"
  CURL_BODY=$(curl --max-time 10 --silent -L "https://${DOMAIN}" 2>/dev/null \
    || curl --max-time 10 --silent -L "http://${DOMAIN}" 2>/dev/null \
    || echo "")
  CURL_STATUS_BROKEN=$(curl --max-time 10 --silent -L -o /dev/null -w "%{http_code}" "https://${DOMAIN}" 2>/dev/null || echo "0")

  if echo "${CURL_BODY}" | grep -qi "welcome to nginx"; then
    pass "Public curl https://${DOMAIN} → 'Welcome to nginx' confirmed (HTTP ${CURL_STATUS_BROKEN})"
  elif [[ "${CURL_STATUS_BROKEN}" =~ ^(200|301|302|303|307|308)$ ]]; then
    warn "Public curl returned HTTP ${CURL_STATUS_BROKEN} but no 'Welcome to nginx' body — Cloudflare may be caching/redirecting origin. API-level detection in step 4 is authoritative."
  elif [[ "${CURL_STATUS_BROKEN}" == "0" ]]; then
    warn "Public curl timed out or connection refused for ${DOMAIN}. Domain may not be routed locally. Continuing to API-level detection."
  else
    warn "Public curl returned HTTP ${CURL_STATUS_BROKEN}. Body: ${CURL_BODY:0:150}. Continuing to API-level detection."
  fi

  # ── Step 4: poll router health until unhealthy ───────────────────────────────
  step "4/7  Poll router health until tenant is unhealthy (max 60s)"
  POLL_DETECTED=false
  for i in $(seq 1 12); do
    HEALTH_RESP=$(api_get "/admin/router-health/tenants?hosting_id=${TENANT_ID}&unhealthy_only=false" || echo "")
    UNHEALTHY_COUNT=$(echo "${HEALTH_RESP}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('unhealthy',0))" 2>/dev/null || echo "0")
    TENANT_HEALTHY=$(echo "${HEALTH_RESP}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for r in d.get('results', []):
    if str(r.get('hosting_id','')) == '${TENANT_ID}':
        print(str(r.get('healthy', True)).lower())
        sys.exit(0)
print('true')" 2>/dev/null || echo "true")

    INCIDENT_DETECTED_STR=$(echo "${HEALTH_RESP}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for r in d.get('results', []):
    if str(r.get('hosting_id','')) == '${TENANT_ID}':
        it = r.get('incident_type','')
        rb = r.get('matched_runbook_id','')
        print(f'{it}|{rb}')
        sys.exit(0)
print('|')" 2>/dev/null || echo "|")

    _INC_TYPE="${INCIDENT_DETECTED_STR%|*}"
    _INC_RB="${INCIDENT_DETECTED_STR#*|}"

    log "Poll ${i}/12: healthy=${TENANT_HEALTHY}, unhealthy_count=${UNHEALTHY_COUNT}"

    if [[ "${TENANT_HEALTHY}" == "false" ]] || [[ "${UNHEALTHY_COUNT}" -gt 0 ]]; then
      POLL_DETECTED=true
      INCIDENT_DETECTED=true
      INCIDENT_TYPE="${_INC_TYPE}"
      log "Incident detected at poll ${i}"
      break
    fi
    sleep 5
  done

  if [[ "${POLL_DETECTED}" == "true" ]]; then
    pass "Router health detected tenant ${TENANT_ID} as unhealthy"
  else
    fail "Router health did not detect tenant ${TENANT_ID} as unhealthy within 60s"
    FINAL_STATE="DETECTION_FAILED"
  fi

  # ── Step 5: match runbook ────────────────────────────────────────────────────
  step "5/7  Match runbook via knowledge/match"
  MATCH_RESP=$(api_post "/admin/knowledge/match" '{"text":"Welcome to nginx!","incident_type":"misconfigured_site_content"}')
  MATCHED_RUNBOOK_ID=$(echo "${MATCH_RESP}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
rb = d.get('matched_runbook', d.get('runbook', {})) or {}
print(rb.get('incident_id', d.get('matched_runbook_id', '')))" 2>/dev/null || echo "")

  SAFE_ACTIONS=$(echo "${MATCH_RESP}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
rb = d.get('matched_runbook', d.get('runbook', {})) or {}
print(json.dumps(rb.get('safe_actions', [])))" 2>/dev/null || echo "[]")

  FORBIDDEN_ACTIONS=$(echo "${MATCH_RESP}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
rb = d.get('matched_runbook', d.get('runbook', {})) or {}
print(json.dumps(rb.get('forbidden_actions', [])))" 2>/dev/null || echo "[]")

  EXPECTED_RUNBOOK="WELCOME_TO_NGINX_EMPTY_SITE"
  if [[ "${MATCHED_RUNBOOK_ID}" == "${EXPECTED_RUNBOOK}" ]]; then
    pass "knowledge/match returned expected runbook: ${MATCHED_RUNBOOK_ID}"
  elif [[ -n "${MATCHED_RUNBOOK_ID}" ]]; then
    fail "knowledge/match returned '${MATCHED_RUNBOOK_ID}', expected '${EXPECTED_RUNBOOK}'"
  else
    fail "knowledge/match returned no runbook for 'Welcome to nginx!' text"
  fi

  # ── Step 6: check dashboard health score ─────────────────────────────────────
  step "6/7  Check dashboard health score is degraded"
  DASHBOARD_RESP=$(api_get "/admin/router-health/tenants?unhealthy_only=false" || echo "")
  DASHBOARD_UNHEALTHY=$(echo "${DASHBOARD_RESP}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('unhealthy',0))" 2>/dev/null || echo "0")
  DASHBOARD_SCORE_DURING_INCIDENT="${DASHBOARD_UNHEALTHY}"

  if [[ "${DASHBOARD_UNHEALTHY}" -gt 0 ]]; then
    pass "Dashboard shows ${DASHBOARD_UNHEALTHY} unhealthy tenant(s) — score degraded"
  else
    fail "Dashboard shows 0 unhealthy tenants — score NOT degraded as expected"
  fi

  # ── Step 7: restore ──────────────────────────────────────────────────────────
  step "7/7  Restore original container"
  docker stop "${TENANT_CONTAINER}" 2>/dev/null && log "Stopped chaos container" || true
  docker rm "${TENANT_CONTAINER}" 2>/dev/null && log "Removed chaos container" || true
  CHAOS_CONTAINER_STARTED=false

  docker rename "${BAK_NAME}" "${TENANT_CONTAINER}" 2>/dev/null \
    && log "Renamed ${BAK_NAME} back to ${TENANT_CONTAINER}" \
    || { fail "Could not rename backup container back"; return 1; }

  docker start "${TENANT_CONTAINER}" \
    && log "Started restored container ${TENANT_CONTAINER}" \
    || { fail "Could not start restored container ${TENANT_CONTAINER}"; return 1; }

  ORIGINAL_CONTAINER_BAK=""  # Cleanup handled — no need for EXIT to re-do it
  CONTAINER_MODIFIED=false
  pass "Original container restored and started"

  # Poll for healthy
  log "Waiting for router health to confirm recovery (max 60s)..."
  RECOVERED=false
  for i in $(seq 1 12); do
    HEALTH_RESP=$(api_get "/admin/router-health/tenants?hosting_id=${TENANT_ID}&unhealthy_only=false" || echo "")
    TENANT_HEALTHY=$(echo "${HEALTH_RESP}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for r in d.get('results', []):
    if str(r.get('hosting_id','')) == '${TENANT_ID}':
        print(str(r.get('healthy', False)).lower())
        sys.exit(0)
print('false')" 2>/dev/null || echo "false")

    log "Recovery poll ${i}/12: healthy=${TENANT_HEALTHY}"
    if [[ "${TENANT_HEALTHY}" == "true" ]]; then
      RECOVERED=true
      break
    fi
    sleep 5
  done

  if [[ "${RECOVERED}" == "true" ]]; then
    REPAIR_SUCCESSFUL=true
    pass "Router health confirmed tenant ${TENANT_ID} is healthy after restore"
  else
    fail "Router health did not confirm recovery within 60s"
  fi

  # Final curl check
  sleep 2
  CURL_STATUS_AFTER_REPAIR=$(curl --max-time 10 --silent -o /dev/null -w "%{http_code}" "http://${DOMAIN}" 2>/dev/null || echo "0")
  CURL_BODY_AFTER=$(curl --max-time 10 --silent "http://${DOMAIN}" 2>/dev/null || echo "")

  if echo "${CURL_BODY_AFTER}" | grep -qi "welcome to nginx"; then
    fail "curl still returns 'Welcome to nginx' after restore (HTTP ${CURL_STATUS_AFTER_REPAIR})"
  else
    pass "curl no longer returns 'Welcome to nginx' after restore (HTTP ${CURL_STATUS_AFTER_REPAIR})"
  fi

  FINAL_STATE="COMPLETE"
}

# ─── CASE: empty_mounts ───────────────────────────────────────────────────────
run_empty_mounts() {
  step "1/3  Validate empty mounts detection via knowledge/match"

  MATCH_RESP=$(api_post "/admin/knowledge/match" '{"text":"Mounts=[]","incident_type":"invalid_container_mount"}')
  MATCHED_RUNBOOK_ID=$(echo "${MATCH_RESP}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
rb = d.get('matched_runbook', d.get('runbook', {})) or {}
print(rb.get('incident_id', d.get('matched_runbook_id', '')))" 2>/dev/null || echo "")

  SAFE_ACTIONS=$(echo "${MATCH_RESP}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
rb = d.get('matched_runbook', d.get('runbook', {})) or {}
print(json.dumps(rb.get('safe_actions', [])))" 2>/dev/null || echo "[]")

  FORBIDDEN_ACTIONS=$(echo "${MATCH_RESP}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
rb = d.get('matched_runbook', d.get('runbook', {})) or {}
print(json.dumps(rb.get('forbidden_actions', [])))" 2>/dev/null || echo "[]")

  EXPECTED_RUNBOOK="CONTAINER_WITH_EMPTY_MOUNTS"
  if [[ "${MATCHED_RUNBOOK_ID}" == "${EXPECTED_RUNBOOK}" ]]; then
    INCIDENT_DETECTED=true
    pass "knowledge/match returned expected runbook: ${MATCHED_RUNBOOK_ID}"
  elif [[ -n "${MATCHED_RUNBOOK_ID}" ]]; then
    INCIDENT_DETECTED=true
    fail "knowledge/match returned '${MATCHED_RUNBOOK_ID}', expected '${EXPECTED_RUNBOOK}'"
  else
    fail "knowledge/match returned no runbook for 'Mounts=[]' text"
  fi

  step "2/3  Validate static-repair dry-run endpoint"
  REPAIR_RESP=$(api_post "/admin/router-health/tenants/${TENANT_ID}/static-repair" '{"dry_run":true}')
  REPAIR_OK=$(echo "${REPAIR_RESP}" | python3 -c "import sys,json; d=json.load(sys.stdin); print('true' if d.get('ok',False) or 'preview' in str(d).lower() or 'dry_run' in str(d).lower() else 'false')" 2>/dev/null || echo "false")

  if [[ "${REPAIR_OK}" == "true" ]]; then
    pass "static-repair dry_run=true succeeded for tenant ${TENANT_ID}"
  else
    REPAIR_CODE=$(echo "${REPAIR_RESP}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('detail',{}).get('code','unknown') if isinstance(d.get('detail'),dict) else str(d.get('detail','')))" 2>/dev/null || echo "unknown")
    # Precondition failures are acceptable in dry-run (e.g. not a static hosting)
    if [[ "${REPAIR_CODE}" =~ "not_static_hosting"|"not_nginx_container"|"no_client_content" ]]; then
      pass "static-repair dry_run returned expected precondition failure: ${REPAIR_CODE}"
    else
      fail "static-repair dry_run failed unexpectedly: ${REPAIR_RESP:0:300}"
    fi
  fi

  step "3/3  Check dashboard"
  DASHBOARD_RESP=$(api_get "/admin/router-health/tenants?unhealthy_only=false" || echo "")
  DASHBOARD_UNHEALTHY=$(echo "${DASHBOARD_RESP}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('unhealthy',0))" 2>/dev/null || echo "0")
  DASHBOARD_SCORE_DURING_INCIDENT="${DASHBOARD_UNHEALTHY}"
  pass "Dashboard check complete, unhealthy_count=${DASHBOARD_UNHEALTHY}"

  REPAIR_SUCCESSFUL=true
  FINAL_STATE="COMPLETE"
}

# ─── CASE: delete_route ───────────────────────────────────────────────────────
run_delete_route() {
  YAML_FILE="/opt/traefik-dynamic/tenants-active.yml"
  BACKUP="${YAML_FILE}.chaos_backup_${TS}"

  step "1/5  Validate Traefik YAML exists"
  if [[ ! -f "${YAML_FILE}" ]]; then
    fail "Traefik dynamic YAML not found at ${YAML_FILE} — cannot run delete_route case"
    return 1
  fi
  pass "Traefik YAML found at ${YAML_FILE}"

  if [[ "${DRY_RUN}" == "true" ]]; then
    log "[DRY-RUN] Would delete route for tenant ${TENANT_ID}. Skipping file changes."
    MATCH_RESP=$(api_post "/admin/knowledge/match" '{"text":"public_route_404"}')
    MATCHED_RUNBOOK_ID=$(echo "${MATCH_RESP}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
rb = d.get('matched_runbook', d.get('runbook', {})) or {}
print(rb.get('incident_id', d.get('matched_runbook_id', '')))" 2>/dev/null || echo "")
    [[ -n "${MATCHED_RUNBOOK_ID}" ]] && INCIDENT_DETECTED=true && pass "DRY-RUN: runbook match=${MATCHED_RUNBOOK_ID}" \
      || fail "DRY-RUN: no runbook match for 'public_route_404'"
    REPAIR_SUCCESSFUL=true
    FINAL_STATE="DRY_RUN_COMPLETE"
    return 0
  fi

  step "2/5  Backup and remove route for tenant ${TENANT_ID}"
  cp "${YAML_FILE}" "${BACKUP}"
  log "Backup: ${BACKUP}"
  CONTAINER_MODIFIED=true

  # Remove any line referencing the tenant's container or domain
  sed -i "/${DOMAIN%%.*}/d" "${YAML_FILE}" 2>/dev/null || true
  sed -i "/${TENANT_CONTAINER}/d" "${YAML_FILE}" 2>/dev/null || true
  pass "Route for ${DOMAIN} removed from YAML"
  sleep 2  # Traefik file provider reload

  step "3/5  Verify HTTP 404 for domain"
  CURL_STATUS_BROKEN=$(curl --max-time 10 --silent -o /dev/null -w "%{http_code}" "http://${DOMAIN}" 2>/dev/null || echo "0")
  if [[ "${CURL_STATUS_BROKEN}" == "404" ]] || [[ "${CURL_STATUS_BROKEN}" == "0" ]]; then
    INCIDENT_DETECTED=true
    pass "Domain returns HTTP ${CURL_STATUS_BROKEN} after route deletion (expected)"
  else
    fail "Expected 404/0 after route deletion, got HTTP ${CURL_STATUS_BROKEN}"
  fi

  step "4/5  Trigger router health check and match runbook"
  HEALTH_RESP=$(api_post "/admin/router-health/tenants/check" "{\"hosting_id\":${TENANT_ID}}" || echo "")
  UNHEALTHY_COUNT=$(echo "${HEALTH_RESP}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('unhealthy',0))" 2>/dev/null || echo "0")
  [[ "${UNHEALTHY_COUNT}" -gt 0 ]] && INCIDENT_DETECTED=true && pass "Router health check detected ${UNHEALTHY_COUNT} unhealthy" \
    || fail "Router health check did not detect unhealthy tenants"

  MATCH_RESP=$(api_post "/admin/knowledge/match" '{"text":"public_route_404"}')
  MATCHED_RUNBOOK_ID=$(echo "${MATCH_RESP}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
rb = d.get('matched_runbook', d.get('runbook', {})) or {}
print(rb.get('incident_id', d.get('matched_runbook_id', '')))" 2>/dev/null || echo "")

  SAFE_ACTIONS=$(echo "${MATCH_RESP}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
rb = d.get('matched_runbook', d.get('runbook', {})) or {}
print(json.dumps(rb.get('safe_actions', [])))" 2>/dev/null || echo "[]")

  FORBIDDEN_ACTIONS=$(echo "${MATCH_RESP}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
rb = d.get('matched_runbook', d.get('runbook', {})) or {}
print(json.dumps(rb.get('forbidden_actions', [])))" 2>/dev/null || echo "[]")

  [[ -n "${MATCHED_RUNBOOK_ID}" ]] && pass "Runbook matched: ${MATCHED_RUNBOOK_ID}" \
    || fail "No runbook matched for 'public_route_404'"

  DASHBOARD_RESP=$(api_get "/admin/router-health/tenants?unhealthy_only=false" || echo "")
  DASHBOARD_UNHEALTHY=$(echo "${DASHBOARD_RESP}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('unhealthy',0))" 2>/dev/null || echo "0")
  DASHBOARD_SCORE_DURING_INCIDENT="${DASHBOARD_UNHEALTHY}"

  step "5/5  Restore YAML backup"
  cp "${BACKUP}" "${YAML_FILE}"
  rm -f "${BACKUP}"
  CONTAINER_MODIFIED=false
  log "YAML restored"
  sleep 2

  CURL_STATUS_AFTER_REPAIR=$(curl --max-time 10 --silent -o /dev/null -w "%{http_code}" "http://${DOMAIN}" 2>/dev/null || echo "0")
  if [[ "${CURL_STATUS_AFTER_REPAIR}" == "200" ]] || [[ "${CURL_STATUS_AFTER_REPAIR}" == "301" ]] || [[ "${CURL_STATUS_AFTER_REPAIR}" == "302" ]]; then
    REPAIR_SUCCESSFUL=true
    pass "Route restored, domain returns HTTP ${CURL_STATUS_AFTER_REPAIR}"
  else
    fail "Route restored but domain still returns HTTP ${CURL_STATUS_AFTER_REPAIR} — Traefik may need more time"
    REPAIR_SUCCESSFUL=false
  fi

  FINAL_STATE="COMPLETE"
}

# ─── Dispatch ─────────────────────────────────────────────────────────────────
case "${CASE}" in
  welcome_to_nginx) run_welcome_to_nginx ;;
  empty_mounts)     run_empty_mounts ;;
  delete_route)     run_delete_route ;;
esac

# ─── Summary ──────────────────────────────────────────────────────────────────
echo ""
log "========== RESULT SUMMARY =========="

# OVERALL is gate-based for welcome_to_nginx:
#   Gate 1: incident_detected=true
#   Gate 2: matched_runbook_id=WELCOME_TO_NGINX_EMPTY_SITE
#   Gate 3: dashboard_unhealthy > 0 during incident
#   Gate 4: repair_successful=true
#   Gate 5: recovery confirmed (included in repair_successful)
# Public curl (step 3) is informational — a 301 from Cloudflare is NOT a failure.
#
# For other cases (empty_mounts, delete_route): fall back to step-log scan.

OVERALL_PASS=true

# Step-log scan: any FAIL entry fails the run (WARN entries are non-fatal)
for entry in "${STEP_LOG[@]:-}"; do
  if [[ "${entry}" == FAIL:* ]]; then
    OVERALL_PASS=false
    break
  fi
done

if [[ "${CASE}" == "welcome_to_nginx" && "${OVERALL_PASS}" == "true" ]]; then
  # Explicit gate validation (authoritative for this case)
  GATE_FAIL=""
  [[ "${INCIDENT_DETECTED}" != "true" ]] && GATE_FAIL="gate1_incident_not_detected"
  [[ -z "${GATE_FAIL}" && "${MATCHED_RUNBOOK_ID}" != "WELCOME_TO_NGINX_EMPTY_SITE" ]] && GATE_FAIL="gate2_runbook_mismatch(got=${MATCHED_RUNBOOK_ID:-none})"
  if [[ -z "${GATE_FAIL}" ]]; then
    ds="${DASHBOARD_SCORE_DURING_INCIDENT:-0}"
    [[ "${ds}" == "null" || "${ds}" -eq 0 ]] 2>/dev/null && GATE_FAIL="gate3_dashboard_not_degraded"
  fi
  [[ -z "${GATE_FAIL}" && "${REPAIR_SUCCESSFUL}" != "true" ]] && GATE_FAIL="gate4_repair_not_successful"
  if [[ -n "${GATE_FAIL}" ]]; then
    OVERALL_PASS=false
    log "GATE FAIL: ${GATE_FAIL}"
  fi
fi

if [[ "${OVERALL_PASS}" == "true" ]]; then
  log "OVERALL: PASSED"
else
  log "OVERALL: FAILED"
fi

log "incident_detected:   ${INCIDENT_DETECTED}"
log "matched_runbook_id:  ${MATCHED_RUNBOOK_ID:-n/a}"
log "incident_type:       ${INCIDENT_TYPE:-n/a}"
log "dashboard_unhealthy: ${DASHBOARD_SCORE_DURING_INCIDENT}"
log "repair_successful:   ${REPAIR_SUCCESSFUL}"
log "curl_after_repair:   ${CURL_STATUS_AFTER_REPAIR:-n/a}"
echo ""

# Exit 1 if any step failed
if [[ "${OVERALL_PASS}" == "false" ]]; then
  exit 1
fi

exit 0
