"""
Shared Redis client singleton.

Single point of connection to Redis for the entire application.
All modules that need Redis (token revocation, distributed locks,
rate limiting, AI cache) should import get_redis() from here.

Falls back to None if REDIS_URL is not set — callers must handle
the None case gracefully (in-memory fallback or feature disabled).

Reconnect strategy: get_redis() attempts a lazy reconnect on each
call if the previous connection failed or went stale. Thread-safe
via double-checked locking.
"""
import logging
import os
import threading
from typing import Optional

import redis as redis_lib

logger = logging.getLogger(__name__)

_REDIS_URL = os.getenv("REDIS_URL", "")
_redis: Optional[redis_lib.Redis] = None
_lock = threading.Lock()


def _build_client() -> Optional[redis_lib.Redis]:
    if not _REDIS_URL:
        return None
    try:
        r = redis_lib.from_url(
            _REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
            retry_on_timeout=True,
        )
        r.ping()
        logger.info("Redis: connected (%s)", _REDIS_URL)
        return r
    except Exception as exc:
        logger.error("Redis: connection failed (%s): %s", _REDIS_URL, exc)
        return None


if not _REDIS_URL:
    logger.warning("REDIS_URL not set — Redis features disabled (dev mode)")
else:
    _redis = _build_client()


def get_redis() -> Optional[redis_lib.Redis]:
    """Returns the shared Redis client.

    Attempts a lazy reconnect if the client is None (startup failure or
    previous connection lost). Thread-safe via double-checked locking.
    """
    global _redis
    if _redis is not None:
        return _redis
    if not _REDIS_URL:
        return None
    with _lock:
        if _redis is not None:
            return _redis
        _redis = _build_client()
    return _redis


def invalidate_redis() -> None:
    """Force the next get_redis() call to attempt a fresh reconnect."""
    global _redis
    _redis = None
