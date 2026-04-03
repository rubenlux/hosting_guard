import os
import logging

from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request

logger = logging.getLogger(__name__)

_REDIS_URL = os.getenv("REDIS_URL", "")


def get_tenant_or_ip(request: Request) -> str:
    return request.headers.get("X-API-Key") or get_remote_address(request)


if _REDIS_URL:
    limiter = Limiter(key_func=get_tenant_or_ip, storage_uri=_REDIS_URL)
    logger.info("Rate limiter: backend Redis (%s)", _REDIS_URL)
else:
    limiter = Limiter(key_func=get_tenant_or_ip)
    logger.warning(
        "REDIS_URL no configurado. Rate limiter usando store in-memory. "
        "No sincronizado entre instancias."
    )
