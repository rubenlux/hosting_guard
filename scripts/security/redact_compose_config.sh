#!/usr/bin/env bash
# redact_compose_config.sh
#
# Runs `docker compose config` and redacts secret values so the output can be
# shared in reports, issues, or support tickets without leaking credentials.
#
# What is redacted (case-insensitive key match):
#   DATABASE_URL, REDIS_URL, JWT_SECRET, SECRET_KEY, SMTP_PASS,
#   CLAUDE_API_KEY, OPENAI_API_KEY, MERCADOPAGO_*, API_KEY, TOKEN,
#   PASSWORD, POSTGRES_PASSWORD, MYSQL_*PASSWORD*, MYSQL_ROOT_PASSWORD
#
# Usage:
#   sudo ./scripts/security/redact_compose_config.sh [docker-compose args...]
#
# Examples:
#   sudo ./scripts/security/redact_compose_config.sh
#   sudo ./scripts/security/redact_compose_config.sh -f /opt/deploy/docker-compose.yml
#
# Notes:
#   - Pass extra args (e.g. -f FILE --env-file FILE) after the script name.
#   - Never run `docker compose config` unredacted in shared logs or issue reports.
#   - For full diff audits use this script, not raw compose config.

set -euo pipefail

CYAN='\033[0;36m'; YELLOW='\033[1;33m'; RESET='\033[0m'

# ── redaction patterns ────────────────────────────────────────────────────────
# Each pattern matches a YAML/env line like:   KEY: value  or  KEY=value
# The value is replaced with [REDACTED].
#
# We match:
#   - YAML key-value:  "    KEY: secretvalue"
#   - env-style:       "KEY=secretvalue"
# after the colon/equals, everything to end of line becomes [REDACTED].

_REDACT_PATTERN='(DATABASE_URL|REDIS_URL|JWT_SECRET|SECRET_KEY|SMTP_PASS(WORD)?|'\
'CLAUDE_API_KEY|OPENAI_API_KEY|MERCADOPAGO[_A-Z0-9]*|'\
'API_KEY|API_SECRET|AUTH_TOKEN|ACCESS_TOKEN|REFRESH_TOKEN|'\
'POSTGRES_PASSWORD|MYSQL_ROOT_PASSWORD|MYSQL_PASSWORD|MYSQL_PASSWD|'\
'DB_PASS(WORD)?|REDIS_PASS(WORD)?|ADMIN_PASS(WORD)?|'\
'[A-Z_]*PASSWORD[A-Z_]*|[A-Z_]*TOKEN[A-Z_]*|[A-Z_]*SECRET[A-Z_]*)'

echo -e "${CYAN}[INFO]${RESET} Running: docker compose config $*"
echo -e "${YELLOW}[WARN]${RESET} Output below has secrets redacted — do not share unredacted output."
echo ""

docker compose config "$@" \
  | sed -E \
      "s/^([[:space:]]*)((${_REDACT_PATTERN})[[:space:]]*:[[:space:]]*)(.+)$/\1\2[REDACTED]/I;
       s/^((${_REDACT_PATTERN})[[:space:]]*=[[:space:]]*)(.+)$/\1[REDACTED]/I"
