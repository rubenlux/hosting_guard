from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request

def get_tenant_or_ip(request: Request):
    return request.headers.get("X-API-Key") or get_remote_address(request)

limiter = Limiter(key_func=get_tenant_or_ip)
