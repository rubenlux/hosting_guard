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
