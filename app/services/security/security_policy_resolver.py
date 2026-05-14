"""
SecurityPolicyResolver: reads protection_mode JSONB from hostings, cached in Redis 60s.

Resolved policy dict:
  mode: "off" | "monitor" | "protect"
  enabled: bool
  block_xmlrpc: bool
  rate_limit_wp_login: bool
  block_scanner_paths: bool
  elevated_sensitivity: bool

Mode derivation:
  off     — enabled=false
  protect — enabled=true AND any of block_xmlrpc / rate_limit_wp_login / block_scanner_paths / elevated_sensitivity
  monitor — enabled=true but no block flags set
"""
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_CACHE_TTL = 60
_CACHE_KEY_FMT = "hg:policy:{hosting_id}"

_OFF_POLICY: dict = {
    "mode":                 "off",
    "enabled":              False,
    "block_xmlrpc":         False,
    "rate_limit_wp_login":  False,
    "block_scanner_paths":  False,
    "elevated_sensitivity": False,
}


def _derive_mode(pm: dict) -> str:
    if not pm.get("enabled"):
        return "off"
    if (
        pm.get("block_xmlrpc") or pm.get("rate_limit_wp_login") or pm.get("block_scanner_paths")
        or pm.get("elevated_sensitivity")
        # legacy field names (safety net for old DB rows)
        or pm.get("block_wp_login") or pm.get("block_scanners") or pm.get("block_rate_limit")
    ):
        return "protect"
    return "monitor"


def get_policy(hosting_id: int, conn=None) -> dict:
    """Return resolved protection policy, using Redis cache when available. Never raises."""
    from app.infra.redis_client import get_redis

    cache_key = _CACHE_KEY_FMT.format(hosting_id=hosting_id)
    r = get_redis()

    if r:
        try:
            cached = r.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as exc:
            logger.debug("policy_resolver: cache read failed: %s", exc)

    policy = _fetch_from_db(hosting_id, conn)

    if r:
        try:
            r.setex(cache_key, _CACHE_TTL, json.dumps(policy))
        except Exception as exc:
            logger.debug("policy_resolver: cache write failed: %s", exc)

    return policy


def invalidate_policy(hosting_id: int) -> None:
    """Evict cached policy. Call this after a protection_mode change."""
    from app.infra.redis_client import get_redis
    r = get_redis()
    if not r:
        return
    try:
        r.delete(_CACHE_KEY_FMT.format(hosting_id=hosting_id))
    except Exception:
        pass


def _fetch_from_db(hosting_id: int, conn=None) -> dict:
    own_conn = conn is None
    if own_conn:
        from app.infra.db import get_connection, release_connection
        try:
            conn = get_connection()
        except Exception as exc:
            logger.warning("policy_resolver: db connect failed for hosting_id=%s: %s", hosting_id, exc)
            return dict(_OFF_POLICY)

    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT protection_mode FROM hostings WHERE hosting_id = %s",
            (hosting_id,),
        )
        row = cur.fetchone()
    except Exception as exc:
        logger.warning("policy_resolver: db query failed for hosting_id=%s: %s", hosting_id, exc)
        return dict(_OFF_POLICY)
    finally:
        if own_conn:
            release_connection(conn)  # type: ignore[possibly-undefined]

    if not row:
        return dict(_OFF_POLICY)

    pm = row.get("protection_mode") or {}
    if isinstance(pm, str):
        try:
            pm = json.loads(pm)
        except Exception:
            pm = {}

    return {
        "mode":                 _derive_mode(pm),
        "enabled":              bool(pm.get("enabled", False)),
        "block_xmlrpc":         bool(pm.get("block_xmlrpc", False)),
        "rate_limit_wp_login":  bool(pm.get("rate_limit_wp_login", False)),
        "block_scanner_paths":  bool(pm.get("block_scanner_paths", False)),
        "elevated_sensitivity": bool(pm.get("elevated_sensitivity", False)),
    }
