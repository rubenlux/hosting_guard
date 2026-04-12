"""
Thin wrapper around the Docker CLI.
Centralizes subprocess invocation so callers don't depend on subprocess directly,
and so the implementation can be swapped (e.g. for tests or SDK migration).
"""
import asyncio
import subprocess
import logging

logger = logging.getLogger(__name__)


def run_docker_command(args: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """
    Run a Docker CLI command and return (returncode, stdout, stderr).
    Never raises — errors are captured and returned as returncode=1.

    Usage:
        code, out, err = run_docker_command(["inspect", "--format", "{{.State.Status}}", name])
        if code != 0:
            handle_error(err)
    """
    try:
        result = subprocess.run(
            ["docker"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        logger.error("Docker command timed out after %ds: docker %s", timeout, " ".join(args))
        return 1, "", f"timeout after {timeout}s"
    except Exception as e:
        logger.error("Docker command failed: %s", e)
        return 1, "", str(e)


async def run_docker_command_async(args: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """
    Async version of run_docker_command — runs in a thread executor so it
    never blocks the event loop.  Same return contract: (returncode, stdout, stderr).

    Usage:
        code, out, err = await run_docker_command_async(["restart", name])
        if code != 0:
            handle_error(err)
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: run_docker_command(args, timeout))
