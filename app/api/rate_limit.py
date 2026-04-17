import os
import logging

from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request

logger = logging.getLogger(__name__)

_REDIS_URL = os.getenv("REDIS_URL", "")


def get_user_id_or_ip(request: Request) -> str:
    """
    Rate-limit key function — identifies WHO is making the request.

    Priority:
      1. Authenticated user → "user:<user_id>"  (global limit across all endpoints)
      2. API key header → "key:<X-API-Key>"
      3. Fallback → client IP

    Using user_id means limits are per-account, not per-IP — prevents VPN/proxy
    bypass and correctly throttles users behind NAT or shared IPs.
    """
    # Try to read user_id from the JWT access_token cookie (fast path, no DB)
    token = request.cookies.get("access_token") or request.cookies.get("support_token")
    if token:
        try:
            from jose import jwt as _jwt, JWTError
            from app.api.security import SECRET, ALGO
            payload = _jwt.decode(token, SECRET, algorithms=[ALGO], options={"verify_exp": False})
            uid = payload.get("user_id")
            if uid:
                return f"user:{uid}"
        except Exception:
            pass  # invalid/expired token — fall through to IP

    # Unauthenticated requests: key by X-API-Key or IP
    return request.headers.get("X-API-Key") or get_remote_address(request)


if _REDIS_URL:
    limiter = Limiter(key_func=get_user_id_or_ip, storage_uri=_REDIS_URL)
    logger.info("Rate limiter: backend Redis (%s)", _REDIS_URL)
else:
    limiter = Limiter(key_func=get_user_id_or_ip)
    logger.warning(
        "REDIS_URL no configurado. Rate limiter usando store in-memory. "
        "No sincronizado entre instancias."
    )
