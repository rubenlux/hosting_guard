from unittest.mock import MagicMock, patch
from app.core.execution.engine import ExecutionEngine
from app.core.execution.registry import EXECUTOR_REGISTRY


def test_execution_dry_run_fail():
    engine = ExecutionEngine()
    # restart_service requiere service_name
    action = {"action_type": "restart_service"}
    result = engine.run(action)
    assert result == "DRY_RUN_FAIL"


def test_execution_restart_service_success():
    mock_result = MagicMock()
    mock_result.returncode = 0
    with patch("app.core.execution.executors.subprocess.run", return_value=mock_result):
        engine = ExecutionEngine()
        action = {"action_type": "restart_service", "service_name": "nginx"}
        result = engine.run(action)
    assert result == "EXECUTED"


def test_execution_unknown_action_aborted():
    engine = ExecutionEngine()
    action = {"action_type": "delete_all_databases"}
    result = engine.run(action)
    assert result == "ABORTED"


def test_execution_rollback_simulation(monkeypatch):
    from app.core.execution.executors import RestartServiceExecutor

    # Mocking a failure in execute to trigger rollback
    class FailingExecutor(RestartServiceExecutor):
        def execute(self, action: dict) -> bool:
            return False  # Simula fallo en la ejecución

    monkeypatch.setitem(EXECUTOR_REGISTRY, "restart_service", FailingExecutor())

    engine = ExecutionEngine()
    action = {"action_type": "restart_service", "service_name": "nginx"}

    result = engine.run(action)
    assert result == "ROLLED_BACK"
