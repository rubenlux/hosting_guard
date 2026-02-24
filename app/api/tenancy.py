from dataclasses import dataclass


@dataclass(frozen=True)
class Tenant:
    tenant_id: str
    name: str
