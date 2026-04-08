import asyncio
import subprocess
from datetime import datetime
from typing import Optional

from fastapi import Depends, HTTPException

from app.api.security import verify_token
from app.infra.audit.hosting_repository import HostingRepository

# Formatos válidos para --since de docker logs: "5m", "2h", "3d", "2024-01-15T10:00:00"
import re

_SINCE_REGEX = re.compile(r"^\d+[smhd]$|^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")

hosting_repo = HostingRepository()


async def _run_docker(*args, timeout: int = 30) -> subprocess.CompletedProcess:
    """Ejecuta un comando Docker de forma no bloqueante (sin bloquear el event loop)."""
    loop = asyncio.get_running_loop()
    cmd = list(args)
    return await loop.run_in_executor(
        None,
        lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=timeout),
    )


async def get_hosting_logs(hosting_id: int, since: Optional[str] = None, user: dict = Depends(verify_token)):
    user_id = user.get("user_id")
    hosting = hosting_repo.get_hosting(hosting_id, user_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting not found")

    if since and not _SINCE_REGEX.match(since):
        raise HTTPException(
            status_code=400,
            detail="Formato de 'since' inválido. Usar: '5m', '2h', '3d' o 'YYYY-MM-DDTHH:MM:SS'."
        )

    command = ["docker", "logs"]
    if since:
        command.extend(["--since", since])
    else:
        command.extend(["--tail", "50"])
    command.append(hosting["container_name"])

    try:
        result = await _run_docker(*command, timeout=5)
        logs = result.stdout if result.stdout else result.stderr
        return {
            "logs": logs if logs else "",
            "timestamp": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S'),
        }
    except Exception:
        return {
            "logs": "Error al obtener los logs. Inténtalo de nuevo.",
            "timestamp": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S'),
        }
