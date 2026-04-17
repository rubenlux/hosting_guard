"""
Saturation guard — rejects Docker-heavy requests when the system is under pressure.

Strategy: track in-flight Docker operations with a Redis counter (INCR/DECR).
When the counter exceeds MAX_DOCKER_OPS_INFLIGHT, new requests to Docker
endpoints receive 503 with a Retry-After header.

If Redis is unavailable (dev mode), the guard falls back to an asyncio counter
that protects within a single process.

Usage — add as a FastAPI dependency to any endpoint that runs Docker commands:

    from app.api.saturation_guard import docker_capacity

    @router.post("/hostings/{hosting_id}/restart")
    async def restart(hosting_id: int, _=Depends(docker_capacity), ...):
        ...

Context manager for wrapping the actual Docker call (increments/decrements):

    async with docker_op():
        await run_docker_command_async(...)
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# Maximum concurrent Docker operations across ALL workers.
# Configurable via env var for tuning without code changes.
# Default 20 — Docker daemon degrades heavily above ~40-50 concurrent ops.
import os as _os
MAX_DOCKER_OPS_INFLIGHT = int(_os.getenv("MAX_DOCKER_OPS_INFLIGHT", "20"))

_REDIS_KEY = "system:docker_ops_inflight"

# In-process fallback counter (used when Redis is unavailable)
_local_inflight = 0
_local_lock = asyncio.Lock()


def _get_inflight() -> int:
    from app.infra.redis_client import get_redis
    redis = get_redis()
    if redis:
        try:
            return int(redis.get(_REDIS_KEY) or 0)
        except Exception:
            pass
    return _local_inflight


def _incr_inflight() -> int:
    from app.infra.redis_client import get_redis
    redis = get_redis()
    if redis:
        try:
            return int(redis.incr(_REDIS_KEY))
        except Exception:
            pass
    global _local_inflight
    _local_inflight += 1
    return _local_inflight


def _decr_inflight() -> None:
    from app.infra.redis_client import get_redis
    redis = get_redis()
    if redis:
        try:
            v = redis.decr(_REDIS_KEY)
            # Guard against counter going negative (e.g. after a crash reset)
            if v < 0:
                redis.set(_REDIS_KEY, 0)
        except Exception:
            pass
        return
    global _local_inflight
    _local_inflight = max(0, _local_inflight - 1)


async def docker_capacity() -> None:
    """FastAPI dependency. Raises 503 if Docker operation capacity is exhausted."""
    current = _get_inflight()
    if current >= MAX_DOCKER_OPS_INFLIGHT:
        logger.warning(
            "saturation_guard: rejecting request — %d Docker ops in flight (max=%d)",
            current, MAX_DOCKER_OPS_INFLIGHT,
        )
        raise HTTPException(
            status_code=503,
            detail=(
                f"Sistema ocupado procesando {current} operaciones. "
                "Intenta en unos segundos."
            ),
            headers={"Retry-After": "5"},
        )


@asynccontextmanager
async def docker_op():
    """Async context manager. Wraps a Docker call, tracking it in the inflight counter."""
    _incr_inflight()
    try:
        yield
    finally:
        _decr_inflight()
