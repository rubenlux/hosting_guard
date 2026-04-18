# app/api/routes/health.py
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict
from app.api.security import verify_token, require_role
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

@router.get("/system", dependencies=[Depends(require_role("admin"))])
async def get_system_health():
    """
    Global system health snapshot — admin only.

    Returns aggregated container stats, Redis status, DB pool utilization,
    and in-flight Docker operations. Use this to decide whether the node
    is approaching saturation before scaling or alerting.
    """
    from app.infra.redis_client import get_redis
    from app.api.saturation_guard import _get_inflight, MAX_DOCKER_OPS_INFLIGHT

    # --- Container counts by status ---
    try:
        all_hostings = hosting_repo.get_all_hostings()
        status_counts: Dict[str, int] = {}
        for h in all_hostings:
            s = h.get("status", "unknown")
            status_counts[s] = status_counts.get(s, 0) + 1
    except Exception as exc:
        status_counts = {"error": str(exc)}

    # --- Redis ---
    redis = get_redis()
    redis_ok = False
    if redis:
        try:
            redis.ping()
            redis_ok = True
        except Exception:
            pass

    # --- DB pool ---
    db_pool_info: Dict = {}
    try:
        from app.infra.db import _pool
        if _pool is not None:
            db_pool_info = {
                "minconn": _pool.minconn,
                "maxconn": _pool.maxconn,
            }
    except Exception:
        pass

    # --- Docker ops in-flight ---
    inflight = _get_inflight()

    # --- Docker latency means (from in-process histogram) ---
    docker_latency: Dict = {}
    try:
        from app.observability.metrics import DOCKER_OP_DURATION
        sums: Dict[str, float]  = {}
        counts: Dict[str, float] = {}
        for metric in DOCKER_OP_DURATION.collect():
            for sample in metric.samples:
                op = sample.labels.get("operation", "unknown")
                if sample.name.endswith("_sum"):
                    sums[op] = sample.value
                elif sample.name.endswith("_count"):
                    counts[op] = sample.value
        for op in sums:
            cnt = counts.get(op, 0)
            docker_latency[op] = {
                "mean_seconds": round(sums[op] / cnt, 3) if cnt > 0 else None,
                "total_ops": int(cnt),
            }
    except Exception:
        pass

    # --- Capacity forecast (optional, never blocks the response) ---
    capacity_forecast = None
    from app.api.config import ENABLE_CAPACITY_FORECAST
    if ENABLE_CAPACITY_FORECAST:
        try:
            from app.services.capacity_planner import evaluate_capacity_forecast
            capacity_forecast = evaluate_capacity_forecast()
        except Exception:
            pass

    return {
        "containers": {
            "by_status": status_counts,
            "total": sum(status_counts.values()) if isinstance(status_counts, dict) and "error" not in status_counts else None,
        },
        "docker_ops": {
            "inflight": inflight,
            "max": MAX_DOCKER_OPS_INFLIGHT,
            "utilization_pct": round(inflight / MAX_DOCKER_OPS_INFLIGHT * 100, 1),
            "latency_by_operation": docker_latency,
        },
        "redis": {"connected": redis_ok},
        "db_pool": db_pool_info,
        "capacity_forecast": capacity_forecast,
    }


@router.get("/{hosting_id}/history")
async def get_hosting_health_history(hosting_id: int, limit: int = 24, user: dict = Depends(verify_token)):
    """Obtiene el historial de salud para gráficas."""
    user_id = user.get("user_id")
    hosting = hosting_repo.get_hosting(hosting_id, user_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting not found")
    
    return health_repo.get_health_history(hosting_id, limit=limit)
