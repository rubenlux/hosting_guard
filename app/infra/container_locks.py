"""
Per-container distributed locks via Redis SETNX.

Replaces the previous asyncio.Lock() approach which only worked within a
single process. With multiple uvicorn workers or a separate orchestrator
container, in-process locks don't prevent concurrent Docker operations.

Usage (unchanged from the asyncio version):

    lock = await container_lock("user_42_mysite_a1b2c3")
    if lock.locked():
        raise HTTPException(409, "Operación en progreso...")
    async with lock:
        await run_docker_command_async(["restart", name])

When Redis is unavailable the lock falls back to the original asyncio.Lock
so local development keeps working without a Redis server.
"""
import asyncio
import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

# asyncio fallback — used when Redis is unreachable
_local_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

# TTL in seconds: if the process crashes while holding the lock, Redis
# releases it automatically after this period.
_LOCK_TTL = 30


class _RedisContainerLock:
    """
    Mimics the asyncio.Lock API expected by callers:
      - lock.locked()  → True if currently held in Redis
      - async with lock: ...
    """

    def __init__(self, container_name: str, redis_client):
        self._name = container_name
        self._redis = redis_client
        self._key = f"lock:container:{container_name}"
        self._held = False

    def locked(self) -> bool:
        try:
            return bool(self._redis.exists(self._key))
        except Exception:
            return False

    async def __aenter__(self):
        from fastapi import HTTPException
        acquired = await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._redis.set(self._key, "1", nx=True, ex=_LOCK_TTL)
        )
        if not acquired:
            raise HTTPException(
                status_code=409,
                detail="Operación en progreso para este hosting. Intenta en unos segundos.",
            )
        self._held = True
        return self

    async def __aexit__(self, *_):
        if self._held:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self._redis.delete(self._key)
                )
            except Exception:
                logger.warning("container_lock: failed to release Redis lock for %s", self._name)
            self._held = False


async def container_lock(container_name: str):
    """
    Returns a lock object for the given container.

    If Redis is available → _RedisContainerLock (cross-process).
    Otherwise → asyncio.Lock (single-process fallback).

    Caller pattern:
        lock = await container_lock(name)
        if lock.locked():
            raise HTTPException(409, ...)
        async with lock:
            ...  # safe Docker operation
    """
    from app.infra.redis_client import get_redis
    redis = get_redis()
    if redis is not None:
        return _RedisContainerLock(container_name, redis)
    # fallback — works in dev without Redis
    return _local_locks[container_name]
