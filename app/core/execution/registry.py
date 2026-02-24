from typing import Dict

from app.core.execution.executors import (
    ClearCacheExecutor,
    RestartServiceExecutor,
    RollbackDeployExecutor,
)
from app.core.execution.interfaces import ActionExecutor

EXECUTOR_REGISTRY: Dict[str, ActionExecutor] = {
    "restart_service": RestartServiceExecutor(),
    "clear_cache": ClearCacheExecutor(),
    "rollback_deploy": RollbackDeployExecutor(),
}
