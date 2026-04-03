# app/core/ai_cache.py
import hashlib
import json
import logging
import os
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 86400  # 24 horas
MAX_CACHE_SIZE = 1000       # Máximo de entradas en-memoria para evitar crecimiento ilimitado
_REDIS_PREFIX = "ai_cache:"

# ---------------------------------------------------------------------------
# Backend Redis (opcional) — activado cuando REDIS_URL está configurado.
# Si Redis no está disponible, se cae al cache en-memoria sin romper nada.
# ---------------------------------------------------------------------------

_REDIS_URL = os.getenv("REDIS_URL", "")
_redis = None

if _REDIS_URL:
    try:
        import redis as redis_lib
        _r = redis_lib.from_url(_REDIS_URL, decode_responses=True, socket_connect_timeout=3)
        _r.ping()
        _redis = _r
        logger.info("AI cache backend: Redis (%s)", _REDIS_URL.split("@")[-1] if "@" in _REDIS_URL else _REDIS_URL)
    except Exception as exc:
        logger.warning("AI cache: Redis no disponible (%s). Usando cache en-memoria.", exc)
        _redis = None
else:
    logger.info("AI cache backend: en-memoria (REDIS_URL no configurado)")

# ---------------------------------------------------------------------------
# Cache en-memoria (fallback o modo dev)
# ---------------------------------------------------------------------------

_cache: dict = {}
_lock = threading.Lock()


def _build_cache_key(decision: dict, tenant_id: Optional[str] = None) -> str:
    relevant = {
        "tenant_id": tenant_id or "default",
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


def _purge_expired() -> int:
    """Elimina entradas expiradas del cache en-memoria. Debe llamarse con _lock adquirido."""
    now = time.time()
    expired_keys = [k for k, v in _cache.items() if now - v["ts"] > CACHE_TTL_SECONDS]
    for k in expired_keys:
        del _cache[k]
    return len(expired_keys)


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def get_cached_response(decision: dict, tenant_id: Optional[str] = None) -> Optional[str]:
    key = _build_cache_key(decision, tenant_id)

    if _redis is not None:
        try:
            value = _redis.get(f"{_REDIS_PREFIX}{key}")
            if value is not None:
                logger.info("Cache HIT (Redis) para key %s...", key[:8])
                return value
            return None
        except Exception as exc:
            logger.warning("AI cache Redis GET falló (%s). Consultando en-memoria.", exc)

    # Fallback: en-memoria
    with _lock:
        entry = _cache.get(key)
        if not entry:
            return None
        if time.time() - entry["ts"] > CACHE_TTL_SECONDS:
            del _cache[key]
            logger.info("Cache EXPIRED (memoria) para key %s...", key[:8])
            return None
    logger.info("Cache HIT (memoria) para key %s...", key[:8])
    return entry["response"]


def save_to_cache(decision: dict, response: str, tenant_id: Optional[str] = None) -> None:
    key = _build_cache_key(decision, tenant_id)

    if _redis is not None:
        try:
            _redis.setex(f"{_REDIS_PREFIX}{key}", CACHE_TTL_SECONDS, response)
            logger.info("Cache SAVED (Redis) para key %s...", key[:8])
            return
        except Exception as exc:
            logger.warning("AI cache Redis SET falló (%s). Guardando en-memoria.", exc)

    # Fallback: en-memoria
    with _lock:
        if len(_cache) >= MAX_CACHE_SIZE:
            purged = _purge_expired()
            if purged == 0:
                oldest_key = min(_cache, key=lambda k: _cache[k]["ts"])
                del _cache[oldest_key]
                logger.warning("Cache lleno: eliminada entrada más antigua (LRU)")
        _cache[key] = {"response": response, "ts": time.time()}
        logger.info("Cache SAVED (memoria) para key %s... (%d entries total)", key[:8], len(_cache))


def get_cache_stats() -> dict:
    if _redis is not None:
        try:
            # Contar claves con el prefijo en Redis (scan para no bloquear)
            redis_count = sum(1 for _ in _redis.scan_iter(f"{_REDIS_PREFIX}*"))
            return {
                "backend": "redis",
                "total_cached": redis_count,
                "ttl_hours": CACHE_TTL_SECONDS // 3600,
            }
        except Exception as exc:
            logger.warning("AI cache Redis STATS falló (%s).", exc)

    with _lock:
        now = time.time()
        valid = sum(1 for v in _cache.values() if now - v["ts"] <= CACHE_TTL_SECONDS)
        expired = len(_cache) - valid
    return {
        "backend": "memory",
        "total_cached": len(_cache),
        "valid_entries": valid,
        "expired_entries": expired,
        "ttl_hours": CACHE_TTL_SECONDS // 3600,
        "max_size": MAX_CACHE_SIZE,
    }
