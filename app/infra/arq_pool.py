"""
Arq pool singleton — used by the HTTP layer to enqueue background jobs.

Falls back gracefully to None if REDIS_URL is not set or the connection
fails. Callers must check for None and use run_in_executor as a fallback.
"""
import logging
import os
import urllib.parse
from typing import Optional

logger = logging.getLogger(__name__)

_pool = None

_ARQ_QUEUE = "arq:hg"


def _build_redis_settings():
    from arq.connections import RedisSettings
    redis_url = os.getenv("REDIS_URL", "")
    if not redis_url:
        return None
    p = urllib.parse.urlparse(redis_url)
    return RedisSettings(
        host=p.hostname or "redis",
        port=p.port or 6379,
        password=p.password or None,
    )


async def init_arq_pool() -> None:
    global _pool
    settings = _build_redis_settings()
    if settings is None:
        logger.warning("REDIS_URL not set — Arq disabled, import jobs run in thread executor")
        return
    try:
        from arq import create_pool
        _pool = await create_pool(settings, default_queue_name=_ARQ_QUEUE)
        logger.info("Arq pool: connected")
    except Exception as exc:
        logger.error("Arq pool: init failed (%s) — jobs fall back to thread executor", exc)
        _pool = None


def get_arq_pool():
    return _pool


async def close_arq_pool() -> None:
    global _pool
    if _pool is not None:
        try:
            await _pool.close()
        except Exception:
            pass
        _pool = None
        logger.info("Arq pool: closed")
