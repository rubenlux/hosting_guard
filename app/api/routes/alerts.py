from fastapi import APIRouter, Depends, HTTPException
from app.api.security import verify_token
from app.infra.audit.health_repository import HealthRepository

router = APIRouter()
_health_repo = HealthRepository()

@router.get("/user/alerts")
async def get_user_alerts(limit: int = 20, user: dict = Depends(verify_token)):
    user_id = user.get("user_id")
    alerts = _health_repo.get_user_alerts(user_id, limit=limit)
    return alerts

@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: int, user: dict = Depends(verify_token)):
    user_id = user.get("user_id")
    # Validar propiedad (opcional pero recomendado)
    success = _health_repo.resolve_alert(alert_id)
    if not success:
        raise HTTPException(status_code=500, detail="Error al resolver la alerta")
    return {"status": "resolved"}
