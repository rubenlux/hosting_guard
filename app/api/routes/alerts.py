import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException
from app.api.security import verify_token
from app.infra.audit.health_repository import HealthRepository
from app.infra.audit.hosting_repository import HostingRepository

logger = logging.getLogger(__name__)

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
    success = _health_repo.resolve_alert(alert_id, user_id=user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alerta no encontrada o no pertenece al usuario")
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


@router.get("/dashboard/summary")
async def get_dashboard_summary(user: dict = Depends(verify_token)):
    """
    Endpoint agregado para el dashboard: devuelve hostings (con métricas Docker),
    salud actual, historial de salud, alertas y actividad reciente en una sola llamada.
    Reduce de 2+N×3 requests a 1.
    """
    from app.services.hosting.list_service import list_hostings as _list_hostings

    user_id = user.get("user_id")

    # 1. Hostings con métricas Docker batcheadas (ya lo hace list_hostings internamente)
    hostings = await _list_hostings(user=user)

    active_ids = [h["hosting_id"] for h in hostings if h.get("status") == "active"]

    # 2. Health + history para todos los activos, en paralelo
    loop = asyncio.get_running_loop()

    async def _get_health(hosting_id: int):
        health = await loop.run_in_executor(None, lambda: _health_repo.get_latest_health(hosting_id))
        history = await loop.run_in_executor(None, lambda: _health_repo.get_health_history(hosting_id, limit=24))

        # Repair on read — strong consistency guarantee.
        # If the live score is healthy (>= 90) but the DB still has open critical/warning
        # alerts (e.g. health_checker cycle hasn't fired since recovery), resolve them now.
        # This is a no-op UPDATE when there are no open alerts (rowcount=0), so the cost
        # on every poll is negligible. Pattern: "eventual consistency → consistent on read."
        score = (health or {}).get("score", 100)
        if score >= 90:
            resolved = await loop.run_in_executor(None, lambda: _health_repo.resolve_open_alerts(hosting_id))
            if resolved:
                logger.info(
                    "dashboard repair-on-read: resolved %d stale alert(s) for hosting_id=%s (score=%d)",
                    resolved, hosting_id, score,
                )

        return hosting_id, health, history

    health_results = await asyncio.gather(*[_get_health(hid) for hid in active_ids])

    # Query open router health incidents — overrides health score when routes are down.
    def _get_router_incidents():
        if not active_ids:
            return {}
        from app.infra.db import get_connection, release_connection
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                """
                SELECT hosting_id, incident_type, severity
                FROM system_incidents
                WHERE source_table = 'router_health_guard'
                  AND status = 'open'
                  AND hosting_id = ANY(%s)
                ORDER BY hosting_id, last_seen DESC
                """,
                (active_ids,),
            )
            result = {}
            for row in cur.fetchall():
                hid = row[0]
                if hid not in result:  # keep most-recent per hosting
                    result[hid] = {"incident_type": row[1], "severity": row[2]}
            return result
        except Exception as exc:
            logger.warning("dashboard: router incidents query failed: %s", exc)
            return {}
        finally:
            if conn:
                release_connection(conn)

    router_incidents = await loop.run_in_executor(None, _get_router_incidents)

    health_map = {}
    history_map = {}
    for hosting_id, health, history in health_results:
        base = health or {
            "score": 100, "status": "healthy", "cpu": 0.0, "ram": 0.0,
            "error_count": 0, "warning_count": 0, "trend": "stable",
        }
        ri = router_incidents.get(hosting_id)
        if ri:
            # Router is down — override score to 0 regardless of container/CPU/RAM metrics.
            # public_reachable and router_incident_type flow to the frontend for advisory + badges.
            base = {
                **base,
                "score": 0,
                "status": "critical",
                "public_reachable": False,
                "router_incident_type": ri["incident_type"],
            }
        else:
            base.setdefault("public_reachable", True)

        health_map[hosting_id] = base
        history_map[hosting_id] = [
            {"score": r["score"], "cpu": r["cpu"], "ram": r["ram"], "timestamp": r["created_at"]}
            for r in history
        ]

    # 3. Alertas y actividad reciente en paralelo
    alerts_task = loop.run_in_executor(None, lambda: _health_repo.get_user_alerts(user_id, limit=20))
    orch_task = loop.run_in_executor(None, lambda: _hosting_repo.get_orchestrator_events(user_id, limit=20))
    alerts_raw, orch_events = await asyncio.gather(alerts_task, orch_task)

    hosting_name_map = {h["hosting_id"]: h["name"] for h in hostings}

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
    normalized_health = [
        {
            "id": f"alert_{a['id']}",
            "event_type": a["level"].upper(),
            "message": a["message"],
            "container_name": hosting_name_map.get(a["site_id"], f"site-{a['site_id']}"),
            "cpu_pct": None,
            "mem_pct": None,
            "risk_level": a["level"],
            "source": "health",
            "resolved": bool(a.get("resolved", 0)),
            "created_at": a["created_at"],
        }
        for a in alerts_raw
    ]
    events = sorted(
        normalized_orch + normalized_health,
        key=lambda x: x["created_at"].isoformat() if hasattr(x["created_at"], "isoformat") else x["created_at"],
        reverse=True,
    )[:20]

    return {
        "hostings": hostings,
        "health": health_map,
        "health_history": history_map,
        "alerts": [dict(a) for a in alerts_raw],
        "events": events,
    }
