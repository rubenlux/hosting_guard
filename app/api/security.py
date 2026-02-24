import os

from fastapi import Header, HTTPException, status

API_KEY = os.getenv("API_KEY")


def require_api_key(x_api_key: str = Header(None)) -> None:
    # Si la API_KEY no está configurada en el entorno (modo desarrollo), no bloqueamos.
    if API_KEY is None:
        return

    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
        )
