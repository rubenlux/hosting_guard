import asyncio
import json
import subprocess

from fastapi import Depends

from app.api.security import verify_token
from app.infra.audit.hosting_repository import HostingRepository
from app.infra.redis_client import get_redis

hosting_repo = HostingRepository()

_CACHE_TTL = 20  # seconds


def _cache_key(user_id: int, skip: int, limit: int) -> str:
    return f"hg:list:{user_id}:{skip}:{limit}"


async def _run_docker(*args, timeout: int = 30) -> subprocess.CompletedProcess:
    """Ejecuta un comando Docker de forma no bloqueante (sin bloquear el event loop)."""
    loop = asyncio.get_running_loop()
    cmd  = list(args)
    return await loop.run_in_executor(
        None,
        lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    )


async def list_hostings(skip: int = 0, limit: int = 50, user: dict = Depends(verify_token)):
    user_id: int = user["user_id"]
    loop = asyncio.get_running_loop()

    # --- Redis cache read ---
    redis = get_redis()
    cache_key = _cache_key(user_id, skip, limit)
    if redis is not None:
        try:
            cached = redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    hostings = await loop.run_in_executor(
        None,
        lambda: hosting_repo.get_all_user_hostings_by_user(user_id, limit=limit, skip=skip)
    )
    hostings_list = [dict(h) for h in hostings if h.get("status") != "deleted"]

    if not hostings_list:
        return hostings_list

    status_map = {
        "running":    "active",
        "exited":     "stopped",
        "restarting": "starting",
        "paused":     "paused",
        "created":    "starting",
        "removing":   "stopped",
        "dead":       "error"
    }

    names = [h["container_name"] for h in hostings_list]
    
    # 1. Obtener status (inspect)
    status_by_name = {}
    try:
        res_inspect = await _run_docker(
            "docker", "inspect",
            "--format", "{{.Name}}|{{.State.Status}}",
            *names,
            timeout=10
        )
        for line in res_inspect.stdout.strip().splitlines():
            if "|" in line:
                cname, cstatus = line.lstrip("/").split("|", 1)
                status_by_name[cname.strip()] = cstatus.strip()
    except Exception as e:
        pass

    # 2. Obtener métricas (stats en batch)
    metrics_by_name = {}
    try:
        # Solo pedimos stats de los corriendo para no trabar
        active_names = [n for n in names if status_by_name.get(n) in ("running",)]
        if active_names:
            res_stats = await _run_docker(
                "docker", "stats", "--no-stream",
                "--format", "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}",
                *active_names,
                timeout=15
            )
            for line in res_stats.stdout.strip().splitlines():
                if "|" in line:
                    parts = line.lstrip("/").split("|")
                    if len(parts) >= 3:
                        metrics_by_name[parts[0].strip()] = {
                            "cpu": parts[1].strip(),
                            "memory": parts[2].strip()
                        }
    except Exception as e:
        pass

    # 3. Cruzar info para la UI
    for h in hostings_list:
        cname = h["container_name"]
        docker_status = status_by_name.get(cname)
        h["status"] = status_map.get(docker_status, "not_found") if docker_status else "not_found"
        
        # Métricas o valores por defecto
        if h["status"] == "active" and cname in metrics_by_name:
            h["metrics"] = metrics_by_name[cname]
        else:
            h["metrics"] = {"cpu": "0%", "memory": "0MiB / 0MiB"}

    # --- Redis cache write ---
    if redis is not None:
        try:
            redis.setex(cache_key, _CACHE_TTL, json.dumps(hostings_list))
        except Exception:
            pass

    return hostings_list
