import logging
import os

logger = logging.getLogger(__name__)

APP_ENV = os.getenv("APP_ENV", "development").lower()

# Flag para enriquecimiento con IA
ENABLE_AI_ADVISORY = os.getenv("ENABLE_AI_ADVISORY", "false").lower() == "true"

# Flag para Capacity Forecast en /health/system
ENABLE_CAPACITY_FORECAST = os.getenv("ENABLE_CAPACITY_FORECAST", "true").lower() == "true"

# Flag para ejecución de acciones (Dry-run / Execute)
# PRECAUCIÓN: En producción debe estar en false hasta validar el flujo humano completo.
ENABLE_ACTION_EXECUTION = os.getenv("ENABLE_ACTION_EXECUTION", "false").lower() == "true"

# Flag para exponer /metrics a Prometheus (desactivado por defecto — solo habilitar en red interna)
ENABLE_METRICS = os.getenv("ENABLE_METRICS", "false").lower() == "true"

# Flag para diagnóstico automático con IA (genera ai_diagnosis por incidente)
ENABLE_AI_DIAGNOSTICS = os.getenv("ENABLE_AI_DIAGNOSTICS", "false").lower() == "true"

if ENABLE_ACTION_EXECUTION and APP_ENV == "production":
    logger.critical(
        "ENABLE_ACTION_EXECUTION=true detectado en APP_ENV=production. "
        "La ejecución de acciones está habilitada. Verifica que el flujo de aprobación "
        "humana esté completamente validado antes de continuar."
    )

if ENABLE_ACTION_EXECUTION:
    logger.warning(
        "Ejecución de acciones habilitada (ENABLE_ACTION_EXECUTION=true) en entorno '%s'.",
        APP_ENV,
    )

# IP pública del servidor — used for apex DNS (A record) verification and Traefik custom-domain config
SERVER_IP = os.getenv("SERVER_IP", "")

# ── Tenant Backups (P3A — local storage) ─────────────────────────────────────
BACKUP_ENABLED = os.getenv("BACKUP_ENABLED", "true").lower() == "true"
BACKUP_STORAGE_DRIVER = os.getenv("BACKUP_STORAGE_DRIVER", "local")
BACKUP_LOCAL_DIR = os.getenv("BACKUP_LOCAL_DIR", "/opt/hostingguard-backups")
BACKUP_DATABASE_ENABLED = os.getenv("BACKUP_DATABASE_ENABLED", "true").lower() == "true"
BACKUP_FILES_ENABLED = os.getenv("BACKUP_FILES_ENABLED", "true").lower() == "true"
BACKUP_AUTOMATIC_RETENTION_POLICY = os.getenv("BACKUP_AUTOMATIC_RETENTION_POLICY", "latest_only")
BACKUP_KEEP_LAST_SUCCESSFUL = os.getenv("BACKUP_KEEP_LAST_SUCCESSFUL", "true").lower() == "true"
BACKUP_DELETE_PREVIOUS_AFTER_SUCCESS = os.getenv("BACKUP_DELETE_PREVIOUS_AFTER_SUCCESS", "true").lower() == "true"
BACKUP_MAX_MANUAL_BACKUPS_PER_TENANT = int(os.getenv("BACKUP_MAX_MANUAL_BACKUPS_PER_TENANT", "2"))
BACKUP_PRE_RESTORE_TTL_HOURS = int(os.getenv("BACKUP_PRE_RESTORE_TTL_HOURS", "24"))
BACKUP_MAX_TOTAL_GB = float(os.getenv("BACKUP_MAX_TOTAL_GB", "20"))
BACKUP_MAX_PER_TENANT_GB = float(os.getenv("BACKUP_MAX_PER_TENANT_GB", "2"))
