"""
Thin wrapper around the Docker CLI.
Centralizes subprocess invocation so callers don't depend on subprocess directly,
and so the implementation can be swapped (e.g. for tests or SDK migration).
"""
import asyncio
import os
import subprocess
import logging

# Network name for tenant containers (isolated from platform services).
# Override via TENANT_NETWORK env var if the compose project name differs.
TENANT_NETWORK = os.getenv("TENANT_NETWORK", "deploy_tenant_edge_network")

# Runtime hardening limits applied to every tenant container.
# pids-limit prevents fork-bomb / runaway process trees inside a tenant.
# Tune via env var without rebuilding the image.
TENANT_PIDS_LIMIT = int(os.getenv("TENANT_PIDS_LIMIT", "200"))


def tenant_hardening_flags() -> list[str]:
    """Security and resource-limit flags added to every `docker run` for a tenant container.

    Call as: *tenant_hardening_flags() inside a command list.
    """
    return [
        "--security-opt", "no-new-privileges:true",
        "--pids-limit",   str(TENANT_PIDS_LIMIT),
    ]

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
