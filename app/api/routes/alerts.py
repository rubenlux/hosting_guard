from fastapi import APIRouter, Depends, HTTPException
from app.api.security import verify_token
from app.infra.audit.health_repository import HealthRepository
from app.infra.audit.hosting_repository import HostingRepository

router = APIRouter()
_health_repo = HealthRepository()
_hosting_repo = HostingRepository()

@router.get("/user/alerts")
async def get_user_alerts(limit: int = 20, user: dict = Depends(verify_token)):
    user_id = user.get("user_id")
    alerts = _health_repo.get_user_alerts(user_id, limit=limit)
    return alerts

@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: int, user: dict = Depends(verify_token)):
    user_id = user.get("user_id")
    success = _health_repo.resolve_alert(alert_id)
    if not success:
        raise HTTPException(status_code=500, detail="Error al resolver la alerta")
    return {"status": "resolved"}

@router.get("/user/recent-activity")
async def get_recent_activity(limit: int = 20, user: dict = Depends(verify_token)):
    """
    Combina orchestrator_events + site_alerts para mostrar actividad real
    en el dashboard. Fuente unificada para 'Actividad Reciente'.
    """
    user_id = user.get("user_id")

    # 1. Orchestrator events (throttles, autoscales, restarts)
    orch_events = _hosting_repo.get_orchestrator_events(user_id, limit=limit)
    normalized_orch = [
        {
            "id": f"orch_{e['event_id']}",
            "event_type": e["event_type"],
            "message": e["message"],
            "container_name": e["container_name"],
            "cpu_pct": e.get("cpu_pct"),
            "mem_pct": e.get("mem_pct"),
            "risk_level": e.get("risk_level"),
            "source": "orchestrator",
            "created_at": e["created_at"],
        }
        for e in orch_events
    ]

    # 2. Health alerts (critical/warning detectados por health_checker o diagnóstico)
    health_alerts = _health_repo.get_user_alerts(user_id, limit=limit)

    # Mapear hosting_id → nombre para enriquecer las alertas
    hostings = _hosting_repo.get_user_hostings(user_id)
    hosting_name_map = {h["hosting_id"]: h["name"] for h in hostings}

    normalized_health = [
        {
            "id": f"alert_{a['id']}",
            "event_type": a["level"].upper(),          # "CRITICAL" | "WARNING"
            "message": a["message"],
            "container_name": hosting_name_map.get(a["site_id"], f"site-{a['site_id']}"),
            "cpu_pct": None,
            "mem_pct": None,
            "risk_level": a["level"],
            "source": "health",
            "resolved": bool(a.get("resolved", 0)),
            "created_at": a["created_at"],
        }
        for a in health_alerts
    ]

    # 3. Merge + sort por fecha descendente
    combined = normalized_orch + normalized_health
    combined.sort(key=lambda x: x["created_at"], reverse=True)

    return combined[:limit]
