# app/core/ai_cache.py
import hashlib
import json
import logging
import time

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 86400  # 24 horas
_cache: dict = {}


def _build_cache_key(decision: dict) -> str:
    relevant = {
        "overall_status": decision.get("overall_status"),
        "project_type": decision.get("project_type"),
        "causes": sorted([
            c.get("cause_code", "")
            for c in decision.get("diagnosis", {}).get("probable_causes", [])
        ]),
        "actions": sorted([
            a.get("action_type", "")
            for a in decision.get("actions_evaluation", [])
        ]),
    }
    raw = json.dumps(relevant, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def get_cached_response(decision: dict) -> str | None:
    key = _build_cache_key(decision)
    entry = _cache.get(key)
    if not entry:
        return None
    if time.time() - entry["ts"] > CACHE_TTL_SECONDS:
        del _cache[key]
        logger.info(f"Cache EXPIRED for key {key[:8]}...")
        return None
    logger.info(f"Cache HIT for key {key[:8]}...")
    return entry["response"]


def save_to_cache(decision: dict, response: str) -> None:
    key = _build_cache_key(decision)
    _cache[key] = {"response": response, "ts": time.time()}
    logger.info(f"Cache SAVED for key {key[:8]}... ({len(_cache)} entries total)")


def get_cache_stats() -> dict:
    return {"total_cached": len(_cache), "ttl_hours": CACHE_TTL_SECONDS // 3600}
