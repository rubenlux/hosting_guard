# app/api/routes/health.py
import logging
from fastapi import APIRouter, Depends, HTTPException, Response
from typing import List, Dict
from app.api.security import verify_token, require_role

logger = logging.getLogger(__name__)
from app.infra.audit.health_repository import HealthRepository
from app.infra.audit.hosting_repository import HostingRepository
from app.infra.audit.system_alert_repository import SystemAlertRepository

router = APIRouter(prefix="/health", tags=["Health"])
health_repo = HealthRepository()
hosting_repo = HostingRepository()
system_alert_repo = SystemAlertRepository()

# IMPORTANT: static routes must be registered BEFORE the dynamic /{hosting_id}
# route — FastAPI matches in declaration order. live/ready are public (no auth).

@router.get("/live")
def health_live():
    """Liveness: el proceso está corriendo."""
    return {"status": "alive"}


@router.get("/ready")
async def health_ready(response: Response):
    """Readiness: DB + Redis responden. Retorna 503 si postgres falla."""
    from app.infra.db import get_connection, release_connection
    from app.infra.redis_client import get_redis

    checks: dict = {}

    try:
        conn = get_connection()
        cur = conn._conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        release_connection(conn)
        checks["postgres"] = "ok"
    except Exception as exc:
        logger.error("health_ready: postgres check failed: %s", exc)
        checks["postgres"] = "error"

    try:
        r = get_redis()
        if r is None:
            checks["redis"] = "degraded"
        else:
            r.ping()
            checks["redis"] = "ok"
    except Exception as exc:
        logger.error("health_ready: redis check failed: %s", exc)
        checks["redis"] = "error"

    if checks.get("postgres") != "ok":
        response.status_code = 503
        return {"status": "degraded", "checks": checks}

    return {"status": "ok", "checks": checks}


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

    # --- Prometheus-persisted alerts (authoritative) ---
    system_alerts = []
    _prometheus_components: set = set()
    try:
        for row in system_alert_repo.get_active_alerts():
            system_alerts.append({
                "level": row.get("severity", "warning"),
                "component": row.get("component", "system"),
                "message": row.get("message", row.get("alert_name", "")),
                "alert_name": row.get("alert_name"),
                "fired_at": row.get("fired_at"),
                "source": "prometheus",
            })
            _prometheus_components.add(row.get("component", "system"))
    except Exception as _exc:
        logger.warning("get_active_alerts failed: %s", _exc)

    # --- Local heuristic alerts (supplement Prometheus for infra not yet scraped) ---
    if not redis_ok:
        system_alerts.append({
            "level": "warning",
            "component": "redis",
            "message": "Redis desconectado — rate limiting y locks en modo in-memory",
            "source": "local",
        })
    if not db_pool_info:
        system_alerts.append({
            "level": "critical",
            "component": "db_pool",
            "message": "Pool de base de datos no disponible",
            "source": "local",
        })
    elif db_pool_info.get("active_connections") is not None:
        maxconn = db_pool_info.get("maxconn", 60)
        pct = db_pool_info["active_connections"] / maxconn * 100 if maxconn else 0
        if pct >= 90 and "database" not in _prometheus_components:
            system_alerts.append({
                "level": "critical",
                "component": "db_pool",
                "message": f"DB pool al {round(pct)}% — {db_pool_info['active_connections']}/{maxconn} conexiones activas",
                "source": "local",
            })
        elif pct >= 70 and "database" not in _prometheus_components:
            system_alerts.append({
                "level": "warning",
                "component": "db_pool",
                "message": f"DB pool al {round(pct)}% — {db_pool_info['active_connections']}/{maxconn} conexiones activas",
                "source": "local",
            })
    if (inflight / MAX_DOCKER_OPS_INFLIGHT * 100) >= 80:
        system_alerts.append({
            "level": "warning",
            "component": "docker",
            "message": f"Docker saturado: {inflight}/{MAX_DOCKER_OPS_INFLIGHT} ops en vuelo",
            "source": "local",
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
