from typing import Dict, Protocol


class ActionExecutor(Protocol):
    """
    Contrato para ejecutores de acciones.
    Cada ejecutor debe ser idempotente y seguro.
    """

    def dry_run(self, action: Dict) -> bool:
        """Verifica pre-condiciones sin aplicar cambios."""
        ...

    def execute(self, action: Dict) -> bool:
        """Aplica la acción. Devuelve True si tuvo éxito."""
        ...

    def rollback(self, action: Dict) -> None:
        """Revierte los cambios realizados por execute."""
        ...
