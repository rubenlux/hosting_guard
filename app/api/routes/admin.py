import asyncio
import subprocess
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

import os
from app.api.security import require_role
from app.infra.audit.user_repository import UserRepository
from app.infra.audit.hosting_repository import HostingRepository
from app.infra.audit.pixel_repository import PixelRepository
from app.infra.audit.metrics_repository import MetricsRepository
from app.infra.db import get_connection

router = APIRouter(prefix="/admin", tags=["admin"])

_user_repo    = UserRepository()
_hosting_repo = HostingRepository()
_pixel_repo   = PixelRepository()
_metrics_repo = MetricsRepository()


# Container prefix used by HostingGuard (same as orchestrator.py)
_CONTAINER_PREFIX = "user_"


async def _run_docker(*args, timeout: int = 30) -> subprocess.CompletedProcess:
    """Non-blocking docker CLI call (replicates the helper in hosting.py)."""
    loop = asyncio.get_running_loop()
    cmd = list(args)
    return await loop.run_in_executor(
        None,
        lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=timeout),
    )


@router.get("/users")
def list_all_users(user: dict = Depends(require_role("admin"))):
    return _user_repo.get_all_users()


@router.get("/hostings")
def list_all_hostings(user: dict = Depends(require_role("admin"))):
    return _hosting_repo.get_all_hostings()


@router.get("/hostings/metrics")
async def get_all_hostings_metrics(_: dict = Depends(require_role("admin"))):
    """
    Returns live CPU/RAM from docker stats for every active user container,
    joined with DB hosting info + stored traffic and uptime data.

    How: single `docker stats --no-stream` call → O(1) vs N per-container calls.
    """
    # --- 1. One docker stats call for all containers ---
    docker_stats = {}
    try:
        result = await _run_docker(
            "docker", "stats", "--no-stream",
            "--format", "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.MemPerc}}|{{.NetIO}}",
            timeout=15,
        )
    except Exception:
        result = None

    if result is not None and result.returncode == 0:
        for line in result.stdout.strip().splitlines():
            if "|" not in line:
                continue
            parts = line.split("|")
            if len(parts) < 5:
                continue
            name = parts[0].strip()
            if not name.startswith(_CONTAINER_PREFIX):
                continue
            docker_stats[name] = {
                "cpu":     parts[1].strip(),
                "memory":  parts[2].strip(),
                "mem_pct": parts[3].strip(),
                "net_io":  parts[4].strip(),
            }

    # --- 2. Load all hostings from DB ---
    hostings = _hosting_repo.get_all_hostings()

    # --- 3. Join docker stats + traffic + uptime per hosting ---
    out = []
    for h in hostings:
        container  = h["container_name"]
        hosting_id = h["hosting_id"]

        stats   = docker_stats.get(container, {})
        traffic = _metrics_repo.get_traffic_stats(container, hours=24)
        uptime  = _metrics_repo.get_uptime_percentage(hosting_id, hours=24)
        avg_ms  = _metrics_repo.get_avg_response_ms(hosting_id, hours=24)

        out.append({
            **h,
            "docker": stats,          # cpu, memory, mem_pct, net_io (empty if not running)
            "traffic_24h": traffic,   # total_requests, errors_4xx, errors_5xx
            "uptime_pct": uptime,     # float 0-100 or None if no data
            "avg_response_ms": avg_ms,
        })

    return out


@router.get("/users/{user_id}/full")
def get_user_full(user_id: int, _: dict = Depends(require_role("admin"))):
    profile = _user_repo.get_user_by_id(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    profile.pop("password_hash", None)

    hostings = _hosting_repo.get_user_hostings(user_id)
    activity = _hosting_repo.get_orchestrator_events(user_id, limit=30, skip=0)

    # AI advisory events keyed by tenant_id (= user email in this system)
    tenant_id = profile["email"]
    conn = get_connection()
    cur = conn.cursor()
    decision_events = [
        dict(r) for r in cur.execute(
            "SELECT event_id, timestamp, overall_status, confidence_level, requires_human_attention "
            "FROM decision_events WHERE tenant_id = %s ORDER BY timestamp DESC LIMIT 20",
            (tenant_id,)
        ).fetchall()
    ]
    cur.execute(
        "SELECT execution_id, timestamp, action_type, status "
        "FROM execution_events WHERE tenant_id = %s ORDER BY timestamp DESC LIMIT 20",
        (tenant_id,)
    )
    execution_events = [dict(r) for r in cur.fetchall()]

    cur.execute(
        "SELECT action_event_id, timestamp, action_type, actor, reason "
        "FROM human_action_events WHERE tenant_id = %s ORDER BY timestamp DESC LIMIT 20",
        (tenant_id,)
    )
    human_events = [dict(r) for r in cur.fetchall()]

    # Per-hosting: stored traffic + uptime (no live docker call to keep response fast)
    hosting_details = []
    for h in hostings:
        container  = h["container_name"]
        hosting_id = h["hosting_id"]
        hosting_details.append({
            **h,
            "traffic_24h":    _metrics_repo.get_traffic_stats(container, hours=24),
            "uptime_pct":     _metrics_repo.get_uptime_percentage(hosting_id, hours=24),
            "avg_response_ms": _metrics_repo.get_avg_response_ms(hosting_id, hours=24),
            "uptime_history": _metrics_repo.get_recent_uptime_checks(hosting_id, limit=20),
        })

    return {
        "user": profile,
        "hostings": hosting_details,
        "activity": activity,
        "decision_events": decision_events,
        "execution_events": execution_events,
        "human_events": human_events,
    }


@router.get("/pixel/overview")
def pixel_overview(_: dict = Depends(require_role("admin"))):
    return _pixel_repo.get_overview_admin()


@router.get("/pixel/events")
def pixel_events(limit: int = 100, offset: int = 0, _: dict = Depends(require_role("admin"))):
    return _pixel_repo.get_all_events_admin(limit=limit, offset=offset)


@router.get("/orchestrator/events")
def get_orchestrator_events(limit: int = 200, _: dict = Depends(require_role("admin"))):
    """Eventos globales del orquestador (throttle, autoscale, restart) de todos los usuarios."""
    cur = conn.cursor()
    cur.execute(
        "SELECT oe.event_id, oe.container_name, oe.user_id, oe.event_type, oe.message, oe.created_at, "
        "u.email FROM orchestrator_events oe "
        "LEFT JOIN users u ON oe.user_id = u.user_id "
        "ORDER BY oe.created_at DESC LIMIT %s",
        (limit,)
    )
    rows = cur.fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Admin hosting actions — sin filtro por user_id
# ---------------------------------------------------------------------------

class TerminateRequest(BaseModel):
    reason: str          # obligatorio — quedará en el audit log


def _get_ip(request: Request) -> str:
    for h in ("X-Real-IP", "X-Forwarded-For"):
        v = request.headers.get(h)
        if v:
            return v.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/hostings/{hosting_id}/restart")
async def admin_restart_hosting(
    hosting_id: int,
    request: Request,
    admin: dict = Depends(require_role("admin")),
):
    """Admin reinicia cualquier hosting sin necesitar sesión de soporte."""
    hosting = _hosting_repo.get_hosting_any(hosting_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting no encontrado")
    result = await _run_docker("docker", "restart", hosting["container_name"], timeout=20)
    _hosting_repo.log_orchestrator_event(
        hosting["container_name"], hosting["user_id"],
        "admin_restart",
        f"Reiniciado por admin {admin['email']} desde {_get_ip(request)}",
    )
    return {"ok": True, "status": "restarting", "container": hosting["container_name"]}


@router.post("/hostings/{hosting_id}/stop")
async def admin_stop_hosting(
    hosting_id: int,
    request: Request,
    admin: dict = Depends(require_role("admin")),
):
    """Admin detiene cualquier hosting."""
    hosting = _hosting_repo.get_hosting_any(hosting_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting no encontrado")
    await _run_docker("docker", "stop", hosting["container_name"], timeout=20)
    _hosting_repo.update_hosting_status(hosting_id, "stopped")
    _hosting_repo.log_orchestrator_event(
        hosting["container_name"], hosting["user_id"],
        "admin_stop",
        f"Detenido por admin {admin['email']} desde {_get_ip(request)}",
    )
    return {"ok": True, "status": "stopped", "container": hosting["container_name"]}


@router.post("/hostings/{hosting_id}/start")
async def admin_start_hosting(
    hosting_id: int,
    request: Request,
    admin: dict = Depends(require_role("admin")),
):
    """Admin inicia cualquier hosting detenido."""
    hosting = _hosting_repo.get_hosting_any(hosting_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting no encontrado")
    await _run_docker("docker", "start", hosting["container_name"], timeout=20)
    _hosting_repo.update_hosting_status(hosting_id, "active")
    _hosting_repo.log_orchestrator_event(
        hosting["container_name"], hosting["user_id"],
        "admin_start",
        f"Iniciado por admin {admin['email']} desde {_get_ip(request)}",
    )
    return {"ok": True, "status": "active", "container": hosting["container_name"]}


@router.get("/hostings/{hosting_id}/logs")
async def admin_get_logs(
    hosting_id: int,
    since: Optional[str] = None,
    admin: dict = Depends(require_role("admin")),
):
    """Admin accede a los logs de cualquier hosting."""
    import re
    _SINCE_REGEX = re.compile(r'^\d+[smhd]$|^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$')
    hosting = _hosting_repo.get_hosting_any(hosting_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting no encontrado")
    if since and not _SINCE_REGEX.match(since):
        raise HTTPException(status_code=400, detail="Formato de 'since' inválido. Ej: '5m', '2h'.")

    cmd = ["docker", "logs"]
    if since:
        cmd += ["--since", since]
    else:
        cmd += ["--tail", "100"]
    cmd.append(hosting["container_name"])

    result = await _run_docker(*cmd, timeout=10)
    logs = result.stdout or result.stderr or ""
    return {"logs": logs, "container": hosting["container_name"]}


@router.delete("/hostings/{hosting_id}/terminate")
async def admin_terminate_hosting(
    hosting_id: int,
    body: TerminateRequest,
    request: Request,
    admin: dict = Depends(require_role("admin")),
):
    """
    Terminación forzada por el admin (uso indebido, spam, TOS violation, etc.).
    Elimina el contenedor Docker + el registro en DB.
    Queda registrado en orchestrator_events con la razón.
    """
    hosting = _hosting_repo.get_hosting_any(hosting_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting no encontrado")

    reason = body.reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Se requiere una razón para la terminación.")

    container = hosting["container_name"]

    # 1. Detener y eliminar el contenedor
    await _run_docker("docker", "rm", "-f", container, timeout=15)

    # 2. Si es WordPress, eliminar también el contenedor de DB
    if "_wp_" in container:
        db_container = container.replace("_wp_", "_db_", 1)
        await _run_docker("docker", "rm", "-f", db_container, timeout=15)

    # 3. Registrar en el audit log ANTES de borrar el registro
    _hosting_repo.log_orchestrator_event(
        container, hosting["user_id"],
        "admin_terminate",
        f"TERMINADO por admin {admin['email']} | Razón: {reason} | IP: {_get_ip(request)}",
    )

    # 4. Eliminar el registro de hostings
    _hosting_repo.admin_delete_hosting(hosting_id)

    return {
        "ok": True,
        "terminated": hosting_id,
        "container": container,
        "reason": reason,
        "admin": admin["email"],
        "at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/finance/summary")
def get_finance_summary(_: dict = Depends(require_role("admin"))):
    """Resumen financiero: saldos, distribución de planes."""
    users = _user_repo.get_all_users()
    total_balance = sum(u.get("balance", 0) or 0 for u in users)
    plans = {}
    for u in users:
        p = u.get("plan", "free") or "free"
        plans[p] = plans.get(p, 0) + 1
    return {
        "total_balance": round(total_balance, 2),
        "users_with_balance": sum(1 for u in users if (u.get("balance") or 0) > 0),
        "users_with_payment": sum(1 for u in users if u.get("has_payment_method")),
        "plan_distribution": [{"plan": k, "count": v} for k, v in sorted(plans.items())],
        "top_balances": sorted(
            [{"email": u["email"], "balance": u.get("balance") or 0, "plan": u.get("plan","free")} for u in users],
            key=lambda x: x["balance"], reverse=True
        )[:10],
    }
