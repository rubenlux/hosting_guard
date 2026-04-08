from fastapi import Depends

from app.api.security import verify_token
from app.infra.audit.hosting_repository import HostingRepository

hosting_repo = HostingRepository()


def get_orchestrator_events(skip: int = 0, limit: int = 20, user: dict = Depends(verify_token)):
    user_id = user.get("user_id")
    # Al ser "def" y no "async def", FastAPI lo ejecuta en un ThreadPool
    # y no bloqueamos el hilo principal asíncrono haciendo peticiones síncronas a la DB!
    events = hosting_repo.get_orchestrator_events(user_id, limit=limit, skip=skip)
    return events
