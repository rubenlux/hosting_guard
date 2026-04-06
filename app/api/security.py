import hmac
import os
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import redis as redis_lib
from fastapi import Depends, Header, HTTPException, Request, status
from jose import jwt, JWTError

logger = logging.getLogger(__name__)

API_KEY = os.getenv("API_KEY")

SECRET = os.getenv("JWT_SECRET")
if not SECRET:
    raise RuntimeError("JWT_SECRET no está definido. La aplicación no puede arrancar sin una clave segura.")

ALGO = "HS256"

# --- Revocation store respaldado por Redis ---
# Fallback a store in-memory si REDIS_URL no está configurado (entornos de desarrollo).
_REDIS_URL = os.getenv("REDIS_URL", "")
_redis: Optional[redis_lib.Redis] = None

if _REDIS_URL:
    try:
        _redis = redis_lib.from_url(_REDIS_URL, decode_responses=True, socket_connect_timeout=3)
        _redis.ping()
        logger.info("Revocation store: Redis conectado en %s", _REDIS_URL)
    except Exception as exc:
        logger.critical("No se pudo conectar a Redis (%s): %s. Abortando arranque.", _REDIS_URL, exc)
        raise RuntimeError(f"Redis requerido pero no disponible: {exc}") from exc
else:
    logger.warning(
        "REDIS_URL no configurado. Revocación de tokens usando store in-memory. "
        "NO apto para multi-instancia ni producción."
    )
    _revoked_tokens: dict[str, float] = {}


def revoke_token(jti: str, expires_at: datetime) -> None:
    """
    Marca un token como revocado hasta su expiración natural.
    Usa Redis con TTL cuando está disponible; in-memory como fallback de desarrollo.
    """
    now = datetime.now(timezone.utc)
    ttl_seconds = max(1, int((expires_at - now).total_seconds()))

    if _redis is not None:
        _redis.setex(f"revoked:{jti}", ttl_seconds, "1")
    else:
        # Fallback in-memory: purgar expirados antes de insertar
        _now_ts = now.timestamp()
        stale = [k for k, v in _revoked_tokens.items() if v < _now_ts]
        for k in stale:
            del _revoked_tokens[k]
        _revoked_tokens[jti] = expires_at.timestamp()


def _is_revoked(jti: str) -> bool:
    if _redis is not None:
        return bool(_redis.exists(f"revoked:{jti}"))
    return jti in _revoked_tokens


def create_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    payload = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    payload.update({"jti": str(uuid.uuid4()), "exp": expire, "type": "access"})
    return jwt.encode(payload, SECRET, algorithm=ALGO)


def create_refresh_token(data: dict) -> str:
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=7)
    payload.update({"jti": str(uuid.uuid4()), "exp": expire, "type": "refresh"})
    return jwt.encode(payload, SECRET, algorithm=ALGO)


def _decode_and_validate(token: str) -> dict:
    """Decode + validate a JWT. Raises HTTPException on any failure."""
    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALGO])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    if not payload.get("user_id") or not payload.get("email"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token payload incompleto")

    jti = payload.get("jti")
    if not jti:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido: falta jti")

    if _is_revoked(jti):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revocado")

    return payload


def verify_token(request: Request) -> dict:
    """
    Accepts either a regular access_token or a support_token cookie.
    Support tokens have mode='support' and is_support_session=True in the payload.
    They are non-renewable and expire in 15 minutes.
    """
    # Support token takes precedence when present
    support_token = request.cookies.get("support_token")
    if support_token:
        payload = _decode_and_validate(support_token)
        if payload.get("mode") != "support":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token de soporte inválido")
        payload["is_support_session"] = True
        return payload

    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = _decode_and_validate(token)
    payload["is_support_session"] = False
    return payload


def require_not_support(user: dict = Depends(verify_token)) -> dict:
    """
    Blocks destructive operations during a support session.
    Use as a dependency on endpoints that must not run in support mode:
        user = Depends(require_not_support)
    """
    if user.get("is_support_session"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acción no permitida en modo soporte. Solo lectura.",
        )
    return user


def require_role(*roles: str) -> Callable:
    """
    Dependency factory para proteger endpoints por rol.
    Uso: user=Depends(require_role("admin"))
    """
    def _check(payload: dict = Depends(verify_token)) -> dict:
        if payload.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Se requiere uno de los roles: {', '.join(roles)}",
            )
        return payload
    return _check


def require_api_key(x_api_key: str = Header(None)) -> None:
    if API_KEY is None:
        # En producción esto jamás debería ocurrir — la app debería fallar al arrancar.
        # Aquí lo bloqueamos explícitamente en lugar de dejar pasar silenciosamente.
        logger.critical("API_KEY no configurada. Bloqueando request por seguridad.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio no disponible: configuración incompleta",
        )

    if x_api_key is None or not hmac.compare_digest(x_api_key, API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
        )
