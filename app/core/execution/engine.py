import logging

from app.core.execution.registry import EXECUTOR_REGISTRY

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """
    Motor de ejecución con ciclo de vida seguro:
    Dry-run -> Execute -> (Optional) Rollback
    """

    def run(self, action: dict) -> str:
        action_type = action.get("action_type")
        if not action_type:
            logger.warning("No action_type found in action payload")
            return "ABORTED"

        executor = EXECUTOR_REGISTRY.get(action_type)

        if not executor:
            logger.warning(f"No executor found for action type: {action_type}")
            return "ABORTED"

        # 1. Dry-run (Verificación de pre-condiciones)
        try:
            if not executor.dry_run(action):
                logger.error("Dry-run failed for action: %s", action_type)
                return "DRY_RUN_FAIL"
        except Exception:
            logger.error("Exception during dry-run of %s", action_type, exc_info=True)
            return "DRY_RUN_FAIL"

        # 2. Execute (Aplicación de la acción)
        try:
            ok = executor.execute(action)
            if not ok:
                logger.warning("Execution failed for %s, initiating rollback", action_type)
                return _safe_rollback(executor, action, action_type)
        except Exception:
            logger.error("Execution exception for %s, initiating rollback", action_type, exc_info=True)
            return _safe_rollback(executor, action, action_type)

        return "EXECUTED"


def _safe_rollback(executor, action: dict, action_type: str) -> str:
    """Ejecuta rollback y devuelve el status real — distingue éxito de fallo."""
    try:
        executor.rollback(action)
        return "ROLLED_BACK"
    except Exception:
        logger.critical(
            "Rollback also failed for %s — system may be in inconsistent state",
            action_type,
            exc_info=True,
        )
        return "ROLLBACK_FAILED"
