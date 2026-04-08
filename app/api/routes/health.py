# app/api/routes/health.py
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict
from app.api.security import verify_token
from app.infra.audit.health_repository import HealthRepository
from app.infra.audit.hosting_repository import HostingRepository

router = APIRouter(prefix="/health", tags=["Health"])
health_repo = HealthRepository()
hosting_repo = HostingRepository()

@router.get("/{hosting_id}")
async def get_hosting_health(hosting_id: int, user: dict = Depends(verify_token)):
    """Obtiene el score de salud actual de un hosting."""
    user_id = user.get("user_id")
    hosting = hosting_repo.get_hosting(hosting_id, user_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting not found")
    
    health = health_repo.get_latest_health(hosting_id)
    if not health:
        # Valores por defecto si no hay historial aún
        return {
            "score": 100, 
            "status": "excellent", 
            "color": "green", 
            "trend": "stable",
            "cpu": 0,
            "ram": 0,
            "error_count": 0,
            "warning_count": 0,
            "alert": None
        }
    
    # Calcular tendencia simple comparando con el anterior
    history = health_repo.get_health_history(hosting_id, limit=2)
    trend = "stable"
    if len(history) >= 2:
        prev_score = history[0]["score"]
        curr_score = history[1]["score"]
        if curr_score > prev_score:
            trend = "improving"
        elif curr_score < prev_score:
            trend = "degrading"
            
    return {
        **health,
        "trend": trend,
        "alert": {
            "type": health["alert_type"],
            "message": health["alert_message"]
        } if health.get("alert_type") else None
    }

@router.get("/{hosting_id}/history")
async def get_hosting_health_history(hosting_id: int, limit: int = 24, user: dict = Depends(verify_token)):
    """Obtiene el historial de salud para gráficas."""
    user_id = user.get("user_id")
    hosting = hosting_repo.get_hosting(hosting_id, user_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting not found")
    
    return health_repo.get_health_history(hosting_id, limit=limit)
