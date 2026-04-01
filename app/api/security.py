import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPBearer
from jose import jwt, JWTError

API_KEY = os.getenv("API_KEY")

SECRET = os.getenv("JWT_SECRET", "supersecretkey")
ALGO = "HS256"

security = HTTPBearer()

def create_token(data: dict, expires_delta: Optional[timedelta] = None):
    payload = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        # Access token largo (24 hrs) para evitar logouts constantes en MVP
        expire = datetime.utcnow() + timedelta(days=1)
    payload.update({"exp": expire, "type": "access"})
    return jwt.encode(payload, SECRET, algorithm=ALGO)

def create_refresh_token(data: dict):
    payload = data.copy()
    # Refresh token largo (7 días)
    expire = datetime.utcnow() + timedelta(days=7)
    payload.update({"exp": expire, "type": "refresh"})
    return jwt.encode(payload, SECRET, algorithm=ALGO)

def verify_token(token=Depends(security)):
    try:
        payload = jwt.decode(token.credentials, SECRET, algorithms=[ALGO])
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
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
        return

    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
        )
