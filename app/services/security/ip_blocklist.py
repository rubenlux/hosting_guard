"""
Redis-backed IP blocklist for HostingGuard protection mode.

Key:   hg:blocklist:{hosting_id}:{ip}
Value: JSON {reason, rule_id, blocked_at, ttl_seconds}

All functions are non-blocking: if Redis is unavailable they return
False/None and log a warning without raising.
"""
import json
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

_KEY_PREFIX = "hg:blocklist"
_DEFAULT_TTL = 3600  # 1 hour


def _key(hosting_id: int, ip: str) -> str:
    return f"{_KEY_PREFIX}:{hosting_id}:{ip}"


def block_ip(
    ip: str,
    hosting_id: int,
    reason: str,
    rule_id: str,
    ttl_seconds: int = _DEFAULT_TTL,
) -> bool:
    """
    Add ip to the blocklist for hosting_id. Returns True on success.
    Idempotent: calling again refreshes TTL.
    """
    if not ip:
        return False
    from app.infra.redis_client import get_redis
    r = get_redis()
    if not r:
        return False
    try:
        value = json.dumps({
            "reason":      reason,
            "rule_id":     rule_id,
            "blocked_at":  time.time(),
            "ttl_seconds": ttl_seconds,
        })
        r.setex(_key(hosting_id, ip), ttl_seconds, value)
        logger.info(
            "ip_blocklist: blocked ip=%s hosting_id=%s rule=%s ttl=%ds",
            ip, hosting_id, rule_id, ttl_seconds,
        )
        return True
    except Exception as exc:
        logger.warning("ip_blocklist: block_ip failed ip=%s hosting_id=%s: %s", ip, hosting_id, exc)
        return False


def is_blocked(ip: str, hosting_id: int) -> Optional[dict]:
    """Return the block record if this IP is blocked for this hosting, else None."""
    if not ip:
        return None
    from app.infra.redis_client import get_redis
    r = get_redis()
    if not r:
        return None
    try:
        raw = r.get(_key(hosting_id, ip))
        return json.loads(raw) if raw else None
    except Exception as exc:
        logger.warning("ip_blocklist: is_blocked failed ip=%s hosting_id=%s: %s", ip, hosting_id, exc)
        return None


def clear_ip(ip: str, hosting_id: int) -> bool:
    """Remove an IP from the blocklist. Returns True if it was present."""
    if not ip:
        return False
    from app.infra.redis_client import get_redis
    r = get_redis()
    if not r:
        return False
    try:
        deleted = r.delete(_key(hosting_id, ip))
        return bool(deleted)
    except Exception as exc:
        logger.warning("ip_blocklist: clear_ip failed ip=%s hosting_id=%s: %s", ip, hosting_id, exc)
        return False
