from abc import ABC, abstractmethod
from typing import Dict

class BaseExecutor(ABC):
    """
    Contrato para ejecutores de acciones.
    Cada ejecutor debe ser idempotente y seguro.
    """

    @abstractmethod
    def dry_run(self, action: Dict) -> bool:
        """Verifica pre-condiciones sin aplicar cambios."""
        pass

    @abstractmethod
    def execute(self, action: Dict) -> bool:
        """Aplica la acción. Devuelve True si tuvo éxito."""
        pass

    @abstractmethod
    def rollback(self, action: Dict) -> None:
        """Revierte los cambios realizados por execute."""
        pass
