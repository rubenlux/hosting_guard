from dataclasses import dataclass
from datetime import datetime
from typing import Dict


@dataclass(frozen=True)
class TenantConfigVersion:
    """
    Representa una versión inmutable de configuración (reglas o prompts) por tenant.
    """

    config_id: str
    tenant_id: str
    version: int
    kind: str  # "rules" | "prompt"
    content: Dict
    created_at: datetime
    active: bool
