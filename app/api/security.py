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
    logger.critical("FATAL: JWT_SECRET no está definido. Usando clave de emergencia (DEBUG ONLY).")
    SECRET = "emergency-insecure-secret-key-change-me"

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
        logger.error("No se pudo conectar a Redis (%s): %s. Fallback a in-memory.", _REDIS_URL, exc)
        _revoked_tokens = {}
        _redis = None
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
    Blocks SENSITIVE account mutations during a support session (topup, password, email).
    Technical ops (file edit/delete, hosting restart/delete) are intentionally NOT blocked
    here — support/admin staff must be able to perform them on behalf of the client.
    """
    if user.get("is_support_session"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acción no permitida en modo soporte: operación financiera o de cuenta.",
        )
    return user


def require_support_write(user: dict = Depends(verify_token)) -> dict:
    """
    Used on technical write endpoints (file save/delete, hosting delete).
    - Regular users (no support session): allowed.
    - Support sessions started by admin or support role: allowed.
    - Support sessions started by billing/readonly: blocked.
    """
    if user.get("is_support_session"):
        caller = user.get("caller_role", "")
        if caller not in ("admin", "support"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acción no permitida. Tu rol de soporte no incluye escritura técnica.",
            )
    return user


def require_role(*roles: str) -> Callable:
    """
    Dependency factory para proteger endpoints por rol.
    Uso: user=Depends(require_role("admin"))

    Si hay un support_token activo pero con el rol equivocado (ej: admin consultando
    sus propios endpoints mientras el support_token de karina todavía está en la cookie),
    hace fallback al access_token normal para autorizar la request.
    """
    def _check(request: Request, payload: dict = Depends(verify_token)) -> dict:
        if payload.get("role") in roles:
            return payload

        # Fallback: soporte activo con rol insuficiente → intentar con access_token
        if payload.get("is_support_session"):
            token = request.cookies.get("access_token")
            if token:
                try:
                    admin_payload = _decode_and_validate(token)
                    if admin_payload.get("role") in roles:
                        admin_payload["is_support_session"] = False
                        return admin_payload
                except HTTPException:
                    pass

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Se requiere uno de los roles: {', '.join(roles)}",
        )
    return _check


def create_staff_token(data: dict) -> str:
    """JWT de 8 horas para colaboradores (type='staff')."""
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=8)
    payload.update({"jti": str(uuid.uuid4()), "exp": expire, "type": "staff"})
    return jwt.encode(payload, SECRET, algorithm=ALGO)


def verify_staff_token(request: Request) -> dict:
    """
    Verifica el staff_token cookie. Lanza 401 si está ausente, expirado o revocado.
    También verifica is_active en la DB para que la desactivación sea inmediata.
    """
    token = request.cookies.get("staff_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Staff no autenticado")

    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALGO])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token de staff inválido o expirado")

    if payload.get("type") != "staff":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tipo de token incorrecto")

    jti = payload.get("jti")
    if jti and _is_revoked(jti):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión de staff revocada")

    # Verificar is_active en DB para que la desactivación sea instantánea
    from app.infra.audit.staff_repository import StaffRepository
    staff = StaffRepository().get_staff_by_id(payload.get("staff_id"))
    if not staff or not staff.get("is_active"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Cuenta de staff desactivada")

    return payload


def require_staff_role(*roles: str) -> Callable:
    """
    Dependency factory para proteger endpoints de staff por rol.
    Roles disponibles: support | billing | readonly | admin (superconjunto)
    """
    def _check(payload: dict = Depends(verify_staff_token)) -> dict:
        if payload.get("role") in roles:
            return payload
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Se requiere uno de los roles de staff: {', '.join(roles)}",
        )
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
