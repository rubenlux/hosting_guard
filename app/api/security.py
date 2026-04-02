import os
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPBearer
from jose import jwt, JWTError

logger = logging.getLogger(__name__)

API_KEY = os.getenv("API_KEY")

SECRET = os.getenv("JWT_SECRET")
if not SECRET:
    raise RuntimeError("JWT_SECRET no está definido. La aplicación no puede arrancar sin una clave segura.")
    
ALGO = "HS256"

security = HTTPBearer()

_revoked_tokens: set = set()

def revoke_token(jti: str):
    _revoked_tokens.add(jti)

def create_token(data: dict, expires_delta: Optional[timedelta] = None):
    payload = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    payload.update({"jti": str(uuid.uuid4()), "exp": expire, "type": "access"})
    return jwt.encode(payload, SECRET, algorithm=ALGO)

def create_refresh_token(data: dict):
    payload = data.copy()
    # Refresh token largo (7 días)
    expire = datetime.now(timezone.utc) + timedelta(days=7)
    payload.update({"jti": str(uuid.uuid4()), "exp": expire, "type": "refresh"})
    return jwt.encode(payload, SECRET, algorithm=ALGO)

def verify_token(token=Depends(security)):
    try:
        payload = jwt.decode(token.credentials, SECRET, algorithms=[ALGO])
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )
        if not payload.get("user_id") or not payload.get("email"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token payload incompleto",
            )
        jti = payload.get("jti")
        if jti and jti in _revoked_tokens:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token revocado",
            )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

def require_api_key(x_api_key: str = Header(None)) -> None:
    # Si la API_KEY no está configurada en el entorno (modo desarrollo), no bloqueamos.
    if API_KEY is None:
        logger.critical("API_KEY no configurada. Endpoint desprotegido en producción.")
        return

    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
        )
