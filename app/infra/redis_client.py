"""
Shared Redis client singleton.

Single point of connection to Redis for the entire application.
All modules that need Redis (token revocation, distributed locks,
rate limiting, AI cache) should import get_redis() from here.

Falls back to None if REDIS_URL is not set — callers must handle
the None case gracefully (in-memory fallback or feature disabled).
"""
import logging
import os
from typing import Optional

import redis as redis_lib

logger = logging.getLogger(__name__)

_REDIS_URL = os.getenv("REDIS_URL", "")
_redis: Optional[redis_lib.Redis] = None

if _REDIS_URL:
    try:
        _redis = redis_lib.from_url(
            _REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
            retry_on_timeout=True,
        )
        _redis.ping()
        logger.info("Redis: connected (%s)", _REDIS_URL)
    except Exception as exc:
        logger.error("Redis: connection failed (%s): %s — falling back to None", _REDIS_URL, exc)
        _redis = None
else:
    logger.warning("REDIS_URL not set — Redis features disabled (dev mode)")


def get_redis() -> Optional[redis_lib.Redis]:
    """Returns the shared Redis client, or None if unavailable."""
    return _redis
