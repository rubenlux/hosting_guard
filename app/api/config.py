import os

# Flag para enriquecimiento con IA
ENABLE_AI_ADVISORY = os.getenv("ENABLE_AI_ADVISORY", "false").lower() == "true"

# Flag para ejecución de acciones (Dry-run / Execute)
# PRECAUCIÓN: En producción debe estar en false hasta validar el flujo humano.
ENABLE_ACTION_EXECUTION = os.getenv("ENABLE_ACTION_EXECUTION", "false").lower() == "true"
