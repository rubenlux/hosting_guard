# app/api/routes/health.py
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict
from app.api.security import verify_token, require_role
from app.infra.audit.health_repository import HealthRepository
from app.infra.audit.hosting_repository import HostingRepository

router = APIRouter(prefix="/health", tags=["Health"])
health_repo = HealthRepository()
hosting_repo = HostingRepository()

# IMPORTANT: static routes (/system, /{id}/history) must be registered BEFORE
# the dynamic /{hosting_id} route — FastAPI matches in declaration order.

@router.get("/system", dependencies=[Depends(require_role("admin"))])
async def get_system_health():
    """
    Global system health snapshot — admin only.

    Returns aggregated container stats, Redis status, DB pool utilization,
    and in-flight Docker operations. Use this to decide whether the node
    is approaching saturation before scaling or alerting.
    """
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

    # --- Redis (with lazy-reconnect attempt) ---
    from app.infra.redis_client import get_redis, invalidate_redis
    import os as _os
    redis_client = get_redis()
    redis_ok = False
    if redis_client:
        try:
            redis_client.ping()
            redis_ok = True
        except Exception:
            invalidate_redis()
    elif _os.getenv("REDIS_URL"):
        invalidate_redis()
        redis_client = get_redis()
        if redis_client:
            try:
                redis_client.ping()
                redis_ok = True
            except Exception:
                pass

    # --- DB pool + active connections ---
    db_pool_info: Dict = {}
    try:
        from app.infra.db import _pool, get_connection, release_connection
        if _pool is not None:
            db_pool_info = {
                "minconn": _pool.minconn,
                "maxconn": _pool.maxconn,
            }
            try:
                conn = get_connection()
                try:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT count(*) AS cnt FROM pg_stat_activity WHERE datname = current_database()"
                    )
                    row = cursor.fetchone()
                    db_pool_info["active_connections"] = int(row["cnt"]) if row else None
                finally:
                    release_connection(conn)
            except Exception:
                pass
    except Exception:
        pass

    # --- Docker ops in-flight ---
    inflight = _get_inflight()

    # --- Docker latency means (from in-process histogram) ---
    docker_latency: Dict = {}
    try:
        from app.observability.metrics import DOCKER_OP_DURATION
        sums: Dict[str, float] = {}
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

    # --- Capacity forecast ---
    capacity_forecast = None
    from app.api.config import ENABLE_CAPACITY_FORECAST
    if ENABLE_CAPACITY_FORECAST:
        try:
            from app.services.capacity_planner import evaluate_capacity_forecast
            capacity_forecast = evaluate_capacity_forecast()
        except Exception:
            pass

    # --- Smart system alerts ---
    system_alerts = []
    if not redis_ok:
        system_alerts.append({
            "level": "warning",
            "component": "redis",
            "message": "Redis desconectado — rate limiting y locks en modo in-memory",
        })
    if not db_pool_info:
        system_alerts.append({
            "level": "critical",
            "component": "db_pool",
            "message": "Pool de base de datos no disponible",
        })
    elif db_pool_info.get("active_connections") is not None:
        maxconn = db_pool_info.get("maxconn", 60)
        pct = db_pool_info["active_connections"] / maxconn * 100 if maxconn else 0
        if pct >= 90:
            system_alerts.append({
                "level": "critical",
                "component": "db_pool",
                "message": f"DB pool al {round(pct)}% — {db_pool_info['active_connections']}/{maxconn} conexiones activas",
            })
        elif pct >= 70:
            system_alerts.append({
                "level": "warning",
                "component": "db_pool",
                "message": f"DB pool al {round(pct)}% — {db_pool_info['active_connections']}/{maxconn} conexiones activas",
            })
    if capacity_forecast:
        for resource in ("cpu", "ram", "disk"):
            f = capacity_forecast.get(resource, {})
            if f.get("status") == "critical":
                system_alerts.append({
                    "level": "critical",
                    "component": resource,
                    "message": f"{resource.upper()} crítico: {f.get('hours_left')}h restantes",
                })
            elif f.get("status") == "warning":
                system_alerts.append({
                    "level": "warning",
                    "component": resource,
                    "message": f"{resource.upper()} advertencia: {f.get('hours_left')}h restantes",
                })
        if capacity_forecast.get("containers", {}).get("status") == "critical":
            system_alerts.append({
                "level": "critical",
                "component": "containers",
                "message": f"Slots de contenedores críticos: {capacity_forecast['containers'].get('current')}/{capacity_forecast['containers'].get('max')}",
            })
    if (inflight / MAX_DOCKER_OPS_INFLIGHT * 100) >= 80:
        system_alerts.append({
            "level": "warning",
            "component": "docker",
            "message": f"Docker saturado: {inflight}/{MAX_DOCKER_OPS_INFLIGHT} ops en vuelo",
        })

    overall_status = (
        "critical" if any(a["level"] == "critical" for a in system_alerts)
        else "warning" if system_alerts
        else "healthy"
    )

    return {
        "status": overall_status,
        "alerts": system_alerts,
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


@router.get("/{hosting_id}")
async def get_hosting_health(hosting_id: int, user: dict = Depends(verify_token)):
    """Obtiene el score de salud actual de un hosting."""
    user_id = user.get("user_id")
    hosting = hosting_repo.get_hosting(hosting_id, user_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting not found")

    health = health_repo.get_latest_health(hosting_id)
    if not health:
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
