#!/usr/bin/env bash
# backup.sh — HostingGuard daily backup to Hetzner Storage Box
#
# What it backs up:
#   1. PostgreSQL full dump (pg_dump via docker exec)
#   2. /opt/clients — all user WordPress sites
#   3. /opt/deploy/data — app runtime data
#
# Retention: 7 daily + 4 weekly (stored in separate dirs on Storage Box)
# Schedule: cron daily at 02:00 UTC (see bottom of file)

set -euo pipefail

STORAGEBOX_HOST="u583151.your-storagebox.de"
STORAGEBOX_USER="u583151"
STORAGEBOX_PORT="23"
SSH_KEY="/root/.ssh/storagebox_backup"

POSTGRES_CONTAINER="hosting_guard_db"
POSTGRES_USER="hosting_user"
POSTGRES_DB="hosting_guard"

BACKUP_TMP="/tmp/hg_backup"
DATE=$(date +%Y-%m-%d)
DAY_OF_WEEK=$(date +%u)   # 1=Mon … 7=Sun

LOG_FILE="/var/log/hosting_guard_backup.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

sftp_run() {
    sftp -i "$SSH_KEY" -P "$STORAGEBOX_PORT" \
         -o StrictHostKeyChecking=no \
         -o BatchMode=yes \
         "${STORAGEBOX_USER}@${STORAGEBOX_HOST}" <<EOF
$1
EOF
}

cleanup() { rm -rf "$BACKUP_TMP"; }
trap cleanup EXIT

log "=== HostingGuard Backup START ==="
rm -rf "$BACKUP_TMP"
mkdir -p "$BACKUP_TMP"

# ---------------------------------------------------------------------------
# 1. PostgreSQL dump
# ---------------------------------------------------------------------------
log "Dumping PostgreSQL..."
docker exec "$POSTGRES_CONTAINER" \
    pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
    | gzip > "$BACKUP_TMP/postgres_${DATE}.sql.gz"
log "PostgreSQL dump: $(du -sh "$BACKUP_TMP/postgres_${DATE}.sql.gz" | cut -f1)"

# ---------------------------------------------------------------------------
# 2. WordPress sites (/opt/clients)
# ---------------------------------------------------------------------------
log "Archiving /opt/clients..."
if [ -d /opt/clients ] && [ "$(ls -A /opt/clients 2>/dev/null)" ]; then
    tar -czf "$BACKUP_TMP/clients_${DATE}.tar.gz" -C /opt clients
    log "Clients archive: $(du -sh "$BACKUP_TMP/clients_${DATE}.tar.gz" | cut -f1)"
else
    log "No clients to backup (empty or missing /opt/clients)"
fi

# ---------------------------------------------------------------------------
# 3. App data (/opt/deploy/data)
# ---------------------------------------------------------------------------
log "Archiving /opt/deploy/data..."
if [ -d /opt/deploy/data ] && [ "$(ls -A /opt/deploy/data 2>/dev/null)" ]; then
    tar -czf "$BACKUP_TMP/appdata_${DATE}.tar.gz" -C /opt/deploy data
    log "App data archive: $(du -sh "$BACKUP_TMP/appdata_${DATE}.tar.gz" | cut -f1)"
else
    log "No app data to backup"
fi

# ---------------------------------------------------------------------------
# 4. Upload daily backup
# ---------------------------------------------------------------------------
REMOTE_DAILY="backups/daily/${DATE}"
log "Uploading to ${STORAGEBOX_HOST}:${REMOTE_DAILY} ..."

BATCH="mkdir backups
mkdir backups/daily
mkdir backups/daily/${DATE}
"
for f in "$BACKUP_TMP"/*.gz; do
    [ -f "$f" ] || continue
    BATCH+="put ${f} ${REMOTE_DAILY}/$(basename "$f")
"
done
BATCH+="exit"
sftp_run "$BATCH"
log "Daily upload complete"

# ---------------------------------------------------------------------------
# 5. Weekly snapshot (Sundays only)
# ---------------------------------------------------------------------------
if [ "$DAY_OF_WEEK" -eq 7 ]; then
    REMOTE_WEEKLY="backups/weekly/${DATE}"
    log "Sunday — creating weekly snapshot at ${REMOTE_WEEKLY}..."
    WEEKLY_BATCH="mkdir backups/weekly
mkdir backups/weekly/${DATE}
"
    for f in "$BACKUP_TMP"/*.gz; do
        [ -f "$f" ] || continue
        WEEKLY_BATCH+="put ${f} ${REMOTE_WEEKLY}/$(basename "$f")
"
    done
    WEEKLY_BATCH+="exit"
    sftp_run "$WEEKLY_BATCH"
    log "Weekly snapshot uploaded"
fi

# ---------------------------------------------------------------------------
# 6. Retention pruning
# ---------------------------------------------------------------------------
log "Pruning daily backups older than 7 days..."
CUTOFF_DAILY=$(date -d '7 days ago' +%Y-%m-%d)
sftp_run "ls backups/daily
exit" 2>/dev/null | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' | while read -r dir; do
    if [[ "$dir" < "$CUTOFF_DAILY" ]]; then
        log "  Removing old daily: $dir"
        sftp_run "rm backups/daily/${dir}/postgres_${dir}.sql.gz
rm backups/daily/${dir}/clients_${dir}.tar.gz
rm backups/daily/${dir}/appdata_${dir}.tar.gz
rmdir backups/daily/${dir}
exit" 2>/dev/null || true
    fi
done

log "Pruning weekly backups older than 28 days..."
CUTOFF_WEEKLY=$(date -d '28 days ago' +%Y-%m-%d)
sftp_run "ls backups/weekly
exit" 2>/dev/null | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' | while read -r dir; do
    if [[ "$dir" < "$CUTOFF_WEEKLY" ]]; then
        log "  Removing old weekly: $dir"
        sftp_run "rm backups/weekly/${dir}/postgres_${dir}.sql.gz
rm backups/weekly/${dir}/clients_${dir}.tar.gz
rm backups/weekly/${dir}/appdata_${dir}.tar.gz
rmdir backups/weekly/${dir}
exit" 2>/dev/null || true
    fi
done

log "=== HostingGuard Backup DONE ==="

# Cron (add with: crontab -e):
# 0 2 * * * /opt/hosting_guard/scripts/backup.sh >> /var/log/hosting_guard_backup.log 2>&1
