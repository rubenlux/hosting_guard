#!/usr/bin/env bash
# Backup PostgreSQL database to a local directory (and optionally S3).
#
# Usage:
#   ./scripts/backup.sh
#
# Required env vars (can be set via docker-compose or a secrets manager):
#   DATABASE_URL   — postgres://user:pass@host:5432/dbname
#   BACKUP_DIR     — local directory to write dumps (default: /var/backups/hosting_guard)
#   BACKUP_RETAIN  — number of daily backups to keep (default: 7)
#   S3_BUCKET      — optional s3://bucket/prefix; if set, upload with aws cli
#
# Cron example (daily at 02:00 UTC):
#   0 2 * * * /app/scripts/backup.sh >> /var/log/backup.log 2>&1

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/hosting_guard}"
BACKUP_RETAIN="${BACKUP_RETAIN:-7}"
TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"
DUMP_FILE="${BACKUP_DIR}/pg_dump_${TIMESTAMP}.sql.gz"

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "[backup] ERROR: DATABASE_URL is not set" >&2
  exit 1
fi

mkdir -p "${BACKUP_DIR}"

echo "[backup] Starting dump → ${DUMP_FILE}"
pg_dump "${DATABASE_URL}" | gzip > "${DUMP_FILE}"
echo "[backup] Dump complete ($(du -sh "${DUMP_FILE}" | cut -f1))"

# Upload to S3 if bucket is configured
if [[ -n "${S3_BUCKET:-}" ]]; then
  echo "[backup] Uploading to ${S3_BUCKET}/"
  aws s3 cp "${DUMP_FILE}" "${S3_BUCKET}/$(basename "${DUMP_FILE}")" --storage-class STANDARD_IA
  echo "[backup] S3 upload complete"
fi

# Rotate local backups — keep the N most recent, delete the rest
echo "[backup] Rotating local dumps (retain=${BACKUP_RETAIN})"
find "${BACKUP_DIR}" -maxdepth 1 -name 'pg_dump_*.sql.gz' \
  | sort -r \
  | tail -n "+$((BACKUP_RETAIN + 1))" \
  | xargs -r rm -v

echo "[backup] Done"
