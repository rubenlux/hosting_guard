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
                logger.error(f"Dry-run failed for action: {action_type}")
                return "DRY_RUN_FAIL"
        except Exception as e:
            logger.error(f"Exception during dry-run of {action_type}: {e}")
            return "DRY_RUN_FAIL"

        # 2. Execute (Aplicación de la acción)
        try:
            ok = executor.execute(action)
            if not ok:
                logger.warning(f"Execution failed for {action_type}, initiating rollback")
                executor.rollback(action)
                return "ROLLED_BACK"
        except Exception as e:
            logger.error(f"Execution exception for {action_type}: {e}. Initiating rollback")
            try:
                executor.rollback(action)
            except Exception as re:
                logger.critical(f"Rollback also failed for {action_type}: {re}")
            return "ROLLED_BACK"

        return "EXECUTED"
