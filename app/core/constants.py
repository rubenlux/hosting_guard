# app/core/constants.py

# Clasificaciones de seguridad
CLASSIFICATION_SAFE = "SAFE"
CLASSIFICATION_SENSITIVE = "SENSITIVE"
CLASSIFICATION_PROHIBITED = "PROHIBITED"

# Estados globales del pipeline
STATUS_READY = "ready_for_execution"
STATUS_REQUIRES_HUMAN = "requires_human"
STATUS_BLOCKED = "blocked"
STATUS_UNKNOWN = "unknown"

# Niveles de confianza
CONFIDENCE_LOW = "low"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_HIGH = "high"
