"""
Redis-backed IP / route blocklist for HostingGuard protection mode.

Keys:
  IP block:       hg:blocklist:{hosting_id}:{ip}        → JSON payload
  Route block:    hg:routeblock:{hosting_id}:{route_key} → JSON payload
  IP tracking:    hg:blocklist_set:{hosting_id}          → Redis SET of blocked IPs
  Route tracking: hg:routeblock_set:{hosting_id}         → Redis SET of blocked route_keys

All functions are non-blocking: if Redis is unavailable they return
False/None and log a warning without raising.
"""
import json
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

_KEY_PREFIX        = "hg:blocklist"
_ROUTE_PREFIX      = "hg:routeblock"
_IP_SET_PREFIX     = "hg:blocklist_set"
_ROUTE_SET_PREFIX  = "hg:routeblock_set"
_DEFAULT_TTL = 3600  # 1 hour


def _key(hosting_id: int, ip: str) -> str:
    return f"{_KEY_PREFIX}:{hosting_id}:{ip}"


def _route_key(hosting_id: int, route_key: str) -> str:
    return f"{_ROUTE_PREFIX}:{hosting_id}:{route_key}"


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


# ── Scoped helpers (Phase 4A) ────────────────────────────────────────────────
# These wrap the existing primitives and also maintain tracking sets so that
# admin endpoints can enumerate active blocks per hosting without Redis SCAN.

def block_ip_for_hosting(
    ip: str,
    hosting_id: int,
    reason: str,
    rule_id: str,
    ttl_seconds: int = _DEFAULT_TTL,
) -> bool:
    """Block ip scoped to hosting_id; also tracks it in the IP set."""
    ok = block_ip(ip, hosting_id, reason, rule_id, ttl_seconds)
    if ok:
        from app.infra.redis_client import get_redis
        r = get_redis()
        if r:
            try:
                set_key = f"{_IP_SET_PREFIX}:{hosting_id}"
                r.sadd(set_key, ip)
                r.expire(set_key, ttl_seconds + 60)
            except Exception:
                pass  # non-critical tracking failure
    return ok


def is_ip_blocked_for_hosting(ip: str, hosting_id: int) -> Optional[dict]:
    """Check if ip is blocked for hosting_id. Returns block record or None."""
    return is_blocked(ip, hosting_id)


def clear_ip_for_hosting(ip: str, hosting_id: int) -> bool:
    """Remove ip block for hosting_id; also removes from tracking set."""
    ok = clear_ip(ip, hosting_id)
    from app.infra.redis_client import get_redis
    r = get_redis()
    if r:
        try:
            r.srem(f"{_IP_SET_PREFIX}:{hosting_id}", ip)
        except Exception:
            pass
    return ok


# ── Route blocking (xmlrpc, scanner paths) ───────────────────────────────────

def block_route_for_hosting(
    route_key: str,
    hosting_id: int,
    reason: str,
    rule_id: str,
    ttl_seconds: int = _DEFAULT_TTL,
) -> bool:
    """Block a route key (e.g. 'xmlrpc', 'scanner') for a hosting. Returns True on success."""
    if not route_key:
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
            "route_key":   route_key,
        })
        rk = _route_key(hosting_id, route_key)
        r.setex(rk, ttl_seconds, value)
        set_key = f"{_ROUTE_SET_PREFIX}:{hosting_id}"
        r.sadd(set_key, route_key)
        r.expire(set_key, ttl_seconds + 60)
        logger.info(
            "ip_blocklist: blocked route=%s hosting_id=%s rule=%s ttl=%ds",
            route_key, hosting_id, rule_id, ttl_seconds,
        )
        return True
    except Exception as exc:
        logger.warning(
            "ip_blocklist: block_route_for_hosting failed route=%s hosting_id=%s: %s",
            route_key, hosting_id, exc,
        )
        return False


def is_route_blocked_for_hosting(route_key: str, hosting_id: int) -> Optional[dict]:
    """Return block record if route_key is blocked for hosting_id, else None."""
    if not route_key:
        return None
    from app.infra.redis_client import get_redis
    r = get_redis()
    if not r:
        return None
    try:
        raw = r.get(_route_key(hosting_id, route_key))
        return json.loads(raw) if raw else None
    except Exception as exc:
        logger.warning(
            "ip_blocklist: is_route_blocked failed route=%s hosting_id=%s: %s",
            route_key, hosting_id, exc,
        )
        return None


def clear_route_for_hosting(route_key: str, hosting_id: int) -> bool:
    """Remove a route block for a hosting."""
    if not route_key:
        return False
    from app.infra.redis_client import get_redis
    r = get_redis()
    if not r:
        return False
    try:
        deleted = r.delete(_route_key(hosting_id, route_key))
        r.srem(f"{_ROUTE_SET_PREFIX}:{hosting_id}", route_key)
        return bool(deleted)
    except Exception as exc:
        logger.warning(
            "ip_blocklist: clear_route_for_hosting failed route=%s hosting_id=%s: %s",
            route_key, hosting_id, exc,
        )
        return False


# ── Listing (admin / rollback UI) ────────────────────────────────────────────

def list_active_blocks_for_hosting(hosting_id: int) -> list[dict]:
    """Return all active IP and route blocks for a hosting.

    Uses tracking sets to avoid SCAN. Stale set members (whose keys expired)
    are silently skipped and removed from the set.
    """
    from app.infra.redis_client import get_redis
    r = get_redis()
    if not r:
        return []

    results: list[dict] = []
    now = time.time()

    try:
        # IP blocks
        ip_set_key = f"{_IP_SET_PREFIX}:{hosting_id}"
        ips = r.smembers(ip_set_key) or set()
        stale_ips = []
        for raw_ip in ips:
            ip = raw_ip.decode() if isinstance(raw_ip, bytes) else raw_ip
            raw = r.get(_key(hosting_id, ip))
            if raw:
                payload = json.loads(raw)
                results.append({
                    "target_type":  "ip",
                    "target_value": ip,
                    "ttl_remaining": max(0, int(payload.get("ttl_seconds", 0) - (now - payload.get("blocked_at", now)))),
                    **payload,
                })
            else:
                stale_ips.append(ip)
        if stale_ips:
            r.srem(ip_set_key, *stale_ips)

        # Route blocks
        route_set_key = f"{_ROUTE_SET_PREFIX}:{hosting_id}"
        routes = r.smembers(route_set_key) or set()
        stale_routes = []
        for raw_route in routes:
            rk = raw_route.decode() if isinstance(raw_route, bytes) else raw_route
            raw = r.get(_route_key(hosting_id, rk))
            if raw:
                payload = json.loads(raw)
                results.append({
                    "target_type":  "route",
                    "target_value": rk,
                    "ttl_remaining": max(0, int(payload.get("ttl_seconds", 0) - (now - payload.get("blocked_at", now)))),
                    **payload,
                })
            else:
                stale_routes.append(rk)
        if stale_routes:
            r.srem(route_set_key, *stale_routes)

    except Exception as exc:
        logger.warning("ip_blocklist: list_active_blocks_for_hosting failed hosting_id=%s: %s", hosting_id, exc)

    return results
