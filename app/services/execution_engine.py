"""
execution_engine — whitelisted, audited subprocess executor for fix proposals.

Security model:
  - Only actions in _WHITELIST are ever executed.
  - Each action maps to a pure function that builds the final command list
    from the container_name — no user-supplied string interpolation.
  - Commands are passed as lists to subprocess.run() — no shell=True,
    no string concatenation, no injection surface.
  - Timeout is mandatory on all commands (default: 30s per command).

Rollback semantics:
  - If the primary command fails (non-zero exit) or raises, rollback is
    attempted automatically.
  - If rollback itself fails, the error is logged but NOT raised —
    we never mask the original failure with a rollback failure.
  - rolled_back=True in the result means rollback was attempted AND succeeded.

This module is the only place where subprocess execution happens for the
remediation path.  The execution whitelist here and risk_engine._RISK_TABLE
must stay in sync — if an action is in one but not the other, it will be
caught at FixProposal build time (risk_engine.is_auto_executable check).
"""
import asyncio
import logging
import subprocess
from typing import Callable

from app.models.fix import FixProposal, FixExecutionResult

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30  # seconds per command

# ── Execution whitelist ───────────────────────────────────────────────────────
# Maps action_id → function(container_name) → [command_list]
# Only actions registered here can ever be executed.

_WHITELIST: dict[str, Callable[[str], list[str]]] = {
    "nginx_reload":       lambda cn: ["docker", "exec", cn, "nginx", "-s", "reload"],
    "docker_restart":     lambda cn: ["docker", "restart", cn],
    "docker_start":       lambda cn: ["docker", "start", cn],
    "wp_cache_flush":     lambda cn: ["docker", "exec", cn, "wp", "--allow-root", "cache", "flush"],
    "wp_rewrite_flush":   lambda cn: ["docker", "exec", cn, "wp", "--allow-root", "rewrite", "flush", "--hard"],
    "wp_transient_flush": lambda cn: ["docker", "exec", cn, "wp", "--allow-root", "transient", "delete", "--all"],
}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _run_sync(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


async def _run_async(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: _run_sync(cmd, timeout),
    )


async def _attempt_rollback(proposal: FixProposal, timeout: int) -> bool:
    """Run rollback commands. Returns True if all succeeded, False otherwise."""
    builder = _WHITELIST.get(proposal.action)
    if not builder or not proposal.rollback_commands:
        return False

    try:
        rollback_cmd = proposal.rollback_commands
        result = await _run_async(rollback_cmd, timeout)
        if result.returncode != 0:
            logger.warning(
                "Rollback failed for action=%s container=%s: %s",
                proposal.action, proposal.container_name, result.stderr,
            )
            return False
        logger.info(
            "Rollback succeeded for action=%s container=%s",
            proposal.action, proposal.container_name,
        )
        return True
    except Exception as exc:
        logger.warning(
            "Rollback raised for action=%s container=%s: %s",
            proposal.action, proposal.container_name, exc,
        )
        return False


# ── Public API ────────────────────────────────────────────────────────────────

async def execute_fix(
    proposal: FixProposal,
    timeout: int = _DEFAULT_TIMEOUT,
) -> FixExecutionResult:
    """
    Execute a FixProposal and return the result.

    Guards applied (in order):
      1. can_auto_fix must be True.
      2. action must be in the execution whitelist.
      3. The built command must match the proposal's stored command list
         (prevents a tampered proposal from running arbitrary commands).
      4. subprocess.run with list args (no shell=True).
      5. On failure → automatic rollback attempt.

    Never raises — all exceptions are returned as FixExecutionResult(success=False).
    """
    # Guard 1 — proposal must allow auto-fix
    if not proposal.can_auto_fix:
        return FixExecutionResult(
            success=False,
            action=proposal.action,
            error="Fix requires manual intervention — can_auto_fix is False.",
        )

    # Guard 2 — action must be whitelisted
    builder = _WHITELIST.get(proposal.action)
    if builder is None:
        return FixExecutionResult(
            success=False,
            action=proposal.action,
            error=f"Action '{proposal.action}' is not in the execution whitelist.",
        )

    # Guard 3 — verify the built command matches stored proposal commands
    # This prevents a stale/tampered proposal from running different commands.
    expected_cmd = builder(proposal.container_name)
    if expected_cmd != proposal.commands:
        logger.error(
            "Command mismatch for action=%s container=%s — refusing execution. "
            "Expected %r, got %r",
            proposal.action, proposal.container_name, expected_cmd, proposal.commands,
        )
        return FixExecutionResult(
            success=False,
            action=proposal.action,
            error="Command integrity check failed — proposal commands do not match whitelist.",
        )

    # ── Execute ──────────────────────────────────────────────────────────────
    logger.info(
        "Executing fix: action=%s container=%s risk=%s",
        proposal.action, proposal.container_name, proposal.risk_level,
    )

    try:
        result = await _run_async(expected_cmd, timeout)
    except subprocess.TimeoutExpired:
        rolled_back = await _attempt_rollback(proposal, timeout)
        return FixExecutionResult(
            success=False,
            action=proposal.action,
            error=f"Command timed out after {timeout}s.",
            rolled_back=rolled_back,
        )
    except Exception as exc:
        rolled_back = await _attempt_rollback(proposal, timeout)
        return FixExecutionResult(
            success=False,
            action=proposal.action,
            error=str(exc),
            rolled_back=rolled_back,
        )

    # ── Evaluate exit code ───────────────────────────────────────────────────
    if result.returncode != 0:
        logger.warning(
            "Fix command failed: action=%s rc=%d stderr=%s",
            proposal.action, result.returncode, result.stderr[:200],
        )
        rolled_back = await _attempt_rollback(proposal, timeout)
        return FixExecutionResult(
            success=False,
            action=proposal.action,
            stdout=result.stdout,
            stderr=result.stderr,
            error=f"Command exited with code {result.returncode}.",
            rolled_back=rolled_back,
        )

    logger.info(
        "Fix succeeded: action=%s container=%s",
        proposal.action, proposal.container_name,
    )
    return FixExecutionResult(
        success=True,
        action=proposal.action,
        stdout=result.stdout,
        stderr=result.stderr,
    )
