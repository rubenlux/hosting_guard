import asyncio
import subprocess

from fastapi import Depends, HTTPException

from app.api.security import verify_token
from app.infra.audit.hosting_repository import HostingRepository

hosting_repo = HostingRepository()


async def _run_docker(*args, timeout: int = 30) -> subprocess.CompletedProcess:
    """Ejecuta un comando Docker de forma no bloqueante (sin bloquear el event loop)."""
    loop = asyncio.get_running_loop()
    cmd = list(args)
    return await loop.run_in_executor(
        None,
        lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=timeout),
    )


async def get_hosting_metrics(hosting_id: int, user: dict = Depends(verify_token)):
    user_id = user.get("user_id")
    hosting = hosting_repo.get_hosting(hosting_id, user_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting not found")

    try:
        # FIX #1: async docker
        result = await _run_docker(
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{.CPUPerc}}|{{.MemUsage}}",
            hosting["container_name"],
            timeout=10,
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split("|")
            if len(parts) >= 2:
                return {"cpu": parts[0], "memory": parts[1]}
        return {"cpu": "0%", "memory": "0MiB / 0MiB"}
    except Exception as e:
        return {"error": str(e)}
