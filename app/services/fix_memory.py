"""
fix_memory — short-lived cache for FixProposal objects.

Keys by (hosting_id, fingerprint) — same fingerprint used by AIDiagnosisRepository,
so the fix proposal is always tied to the exact diagnosis snapshot that produced it.

TTL: 1 hour.  Fix proposals are cheap to rebuild so we use a shorter TTL
than the 24h diagnosis cache — system state can change between diagnoses.

Backend:
  Redis when REDIS_URL is set (same connection as ai_cache.py).
  Thread-safe in-memory dict as fallback.

The interface is intentionally synchronous (called from async contexts via
run_in_executor) to match the pattern established in diagnose_service.py.
"""
import json
import logging
import os
import threading
import time
from typing import Optional

from app.models.fix import FixProposal

logger = logging.getLogger(__name__)

_TTL = 3600           # 1 hour
_REDIS_PREFIX = "fix_proposal:"
_MAX_MEMORY_ENTRIES = 500

# ── Redis (optional) ──────────────────────────────────────────────────────────

_redis = None
_REDIS_URL = os.getenv("REDIS_URL", "")

if _REDIS_URL:
    try:
        import redis as redis_lib
        _r = redis_lib.from_url(_REDIS_URL, decode_responses=True, socket_connect_timeout=3)
        _r.ping()
        _redis = _r
        logger.info("fix_memory: Redis backend active")
    except Exception as exc:
        logger.warning("fix_memory: Redis unavailable (%s) — using in-memory cache", exc)

# ── In-memory fallback ────────────────────────────────────────────────────────

_store: dict[str, dict] = {}
_lock = threading.Lock()


def _key(hosting_id: int, fingerprint: str) -> str:
    return f"{_REDIS_PREFIX}{hosting_id}:{fingerprint}"


# ── Public API ────────────────────────────────────────────────────────────────

def get_proposal(hosting_id: int, fingerprint: str) -> Optional[FixProposal]:
    """Return a cached FixProposal or None on miss/error."""
    k = _key(hosting_id, fingerprint)

    if _redis is not None:
        try:
            raw = _redis.get(k)
            if raw:
                return FixProposal(**json.loads(raw))
            return None
        except Exception as exc:
            logger.warning("fix_memory Redis GET failed (%s) — falling back to memory", exc)

    with _lock:
        entry = _store.get(k)
        if not entry:
            return None
        if time.time() - entry["ts"] > _TTL:
            del _store[k]
            return None
        return FixProposal(**entry["data"])


def save_proposal(proposal: FixProposal) -> None:
    """Persist a FixProposal to cache. Silently ignores errors."""
    k = _key(proposal.hosting_id, proposal.fingerprint)
    raw = proposal.model_dump()

    if _redis is not None:
        try:
            _redis.setex(k, _TTL, json.dumps(raw))
            return
        except Exception as exc:
            logger.warning("fix_memory Redis SET failed (%s) — falling back to memory", exc)

    with _lock:
        # Evict oldest entry if at capacity
        if len(_store) >= _MAX_MEMORY_ENTRIES:
            oldest = min(_store, key=lambda x: _store[x]["ts"])
            del _store[oldest]
        _store[k] = {"data": raw, "ts": time.time()}


def delete_proposal(hosting_id: int, fingerprint: str) -> None:
    """Invalidate a cached proposal (e.g. after successful execution)."""
    k = _key(hosting_id, fingerprint)

    if _redis is not None:
        try:
            _redis.delete(k)
        except Exception as exc:
            logger.warning("fix_memory Redis DELETE failed: %s", exc)
        return

    with _lock:
        _store.pop(k, None)
