import asyncio
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

import os
from app.api.security import require_role
from app.infra.audit.user_repository import UserRepository
from app.infra.audit.hosting_repository import HostingRepository
from app.infra.audit.pixel_repository import PixelRepository
from app.infra.audit.metrics_repository import MetricsRepository
from app.infra.audit.repository import AuditRepository

router = APIRouter(prefix="/admin", tags=["admin"])

_user_repo    = UserRepository()
_hosting_repo = HostingRepository()
_audit_repo   = AuditRepository()
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
    tenant_id        = profile["email"]
    decision_events  = _audit_repo.get_decision_events(tenant_id, limit=20)
    execution_events = _audit_repo.get_execution_events(tenant_id, limit=20)
    human_events     = _audit_repo.get_human_action_events(tenant_id, limit=20)

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
    return _hosting_repo.get_all_orchestrator_events(limit=limit)


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


@router.get("/metrics/node")
def get_node_metrics(_: dict = Depends(require_role("admin"))):
    """Real node metrics queried from Prometheus (node_exporter data)."""
    import os
    import requests as _req

    PROM = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")

    QUERIES = {
        "cpu_pct":  '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[2m])) * 100)',
        "ram_pct":  "(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100",
        "disk_pct": '(1 - node_filesystem_avail_bytes{fstype!~"tmpfs|overlay",mountpoint="/"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay",mountpoint="/"}) * 100',
    }

    result = {"source": "prometheus", "available": False}

    try:
        values = {}
        for key, query in QUERIES.items():
            resp = _req.get(f"{PROM}/api/v1/query", params={"query": query}, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            series = data.get("data", {}).get("result", [])
            if series:
                values[key] = round(float(series[0]["value"][1]), 1)
            else:
                values[key] = None

        result.update({
            "available": True,
            "cpu_pct":   values.get("cpu_pct"),
            "ram_pct":   values.get("ram_pct"),
            "disk_pct":  values.get("disk_pct"),
        })
    except Exception as exc:
        result["error"] = str(exc)

    return result


@router.get("/metrics/capacity")
def get_capacity_metrics(_: dict = Depends(require_role("admin"))):
    """Unified capacity snapshot for the SystemStatusBanner."""
    try:
        from app.services.capacity_planner import evaluate_capacity_forecast
        f = evaluate_capacity_forecast()
    except Exception:
        return {"status": "unknown", "capacity_score": None, "recommendation": "ok"}

    return {
        "status":             f.get("overall_status", "ok"),
        "capacity_score":     f.get("capacity_score"),
        "cpu_pct":            f["cpu"].get("usage"),
        "ram_pct":            f["ram"].get("usage"),
        "disk_pct":           f["disk"].get("usage"),
        "containers": {
            "used":     f["containers"].get("current"),
            "capacity": f["containers"].get("max"),
            "pct":      f["containers"].get("usage"),
        },
        "days_to_exhaustion": f.get("days_to_exhaustion"),
        "recommendation":     f.get("recommendation", "ok"),
    }


@router.get("/ops-summary")
def get_ops_summary(_: dict = Depends(require_role("admin"))):
    """Operational snapshot: free tier, cleanup stats, and business KPIs."""
    from app.api.routes.hosting import MAX_FREE_USERS

    users = _user_repo.get_all_users()
    free_users  = [u for u in users if u.get("plan") == "free"]
    paid_users  = [u for u in users if u.get("plan") not in ("free", None)]

    try:
        free_active  = _hosting_repo.count_active_free_users()
        deleted_today = _hosting_repo.count_deleted_today()
        zombie_count  = _hosting_repo.count_by_status("zombie")
        expired_count = _hosting_repo.count_by_status("expired")
    except Exception:
        free_active = deleted_today = zombie_count = expired_count = 0

    total_balance = sum(u.get("balance", 0) or 0 for u in users)

    return {
        "free_tier": {
            "active_users":  free_active,
            "cap":           MAX_FREE_USERS,
            "cap_pct":       round(free_active / MAX_FREE_USERS * 100, 1),
            "expired_ready": expired_count,
            "deleted_today": deleted_today,
            "zombies":       zombie_count,
        },
        "business": {
            "total_users":  len(users),
            "paid_users":   len(paid_users),
            "free_users":   len(free_users),
            "conversion_pct": round(len(paid_users) / len(users) * 100, 1) if users else 0,
            "total_balance": round(total_balance, 2),
        },
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


# ── Plan Management ─────────────────────────────────────────────────────────

_VALID_PAID_PLANS = {"personal", "negocio", "agencia"}
_PLAN_RESOURCES = {
    "personal": {"cpu": "0.5",  "memory": "512m"},
    "negocio":  {"cpu": "1",    "memory": "1g"},
    "agencia":  {"cpu": "2",    "memory": "2g"},
}
_FREE_FOREVER_DATE = "2099-12-31T23:59:59+00:00"


class ExtendPlanBody(BaseModel):
    days: Literal[14, 30]


class UpgradePlanBody(BaseModel):
    plan: str


@router.post("/users/{user_id}/plan/extend")
def admin_extend_free_plan(
    user_id: int,
    body: ExtendPlanBody,
    admin: dict = Depends(require_role("admin")),
):
    """Extend a free-tier user's trial by 14 or 30 days from today."""
    user = _user_repo.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if user.get("plan") not in ("free",):
        raise HTTPException(status_code=400, detail="Solo se puede extender el período de prueba del plan free")

    # Calculate new expiry: start from current plan_expires_at if set (and not free-forever),
    # otherwise from today. Extend forward by the requested days.
    current_override = user.get("plan_expires_at")
    if current_override and "2099" not in current_override:
        try:
            base = datetime.fromisoformat(current_override.replace("Z", "+00:00"))
            if base.tzinfo is None:
                base = base.replace(tzinfo=timezone.utc)
            # If already in the past, start from now instead
            if base < datetime.now(timezone.utc):
                base = datetime.now(timezone.utc)
        except ValueError:
            base = datetime.now(timezone.utc)
    else:
        base = datetime.now(timezone.utc)

    new_expires_at = (base + timedelta(days=body.days)).isoformat()
    _user_repo.update_plan(user_id, "free", new_expires_at)

    _hosting_repo.log_orchestrator_event(
        container_name="—",
        user_id=user_id,
        event_type="PLAN_EXTENDED",
        message=f"Admin {admin['email']} extendió el plan free por {body.days} días. Nuevo vencimiento: {new_expires_at}",
    )
    return {"ok": True, "plan_expires_at": new_expires_at, "extended_days": body.days}


@router.post("/users/{user_id}/plan/free-forever")
def admin_set_free_forever(
    user_id: int,
    admin: dict = Depends(require_role("admin")),
):
    """Mark a free-tier user as 'free forever' — trial never expires."""
    user = _user_repo.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if user.get("plan") not in ("free",):
        raise HTTPException(status_code=400, detail="Solo aplica a usuarios con plan free")

    _user_repo.update_plan(user_id, "free", _FREE_FOREVER_DATE)
    _hosting_repo.log_orchestrator_event(
        container_name="—",
        user_id=user_id,
        event_type="PLAN_FREE_FOREVER",
        message=f"Admin {admin['email']} marcó al usuario como free forever.",
    )
    return {"ok": True, "plan": "free", "plan_expires_at": _FREE_FOREVER_DATE}


@router.post("/users/{user_id}/plan/deactivate")
def admin_deactivate_free_plan(
    user_id: int,
    admin: dict = Depends(require_role("admin")),
):
    """Force-expire a free-tier user immediately (spam, abuse, policy violation)."""
    user = _user_repo.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if user.get("plan") not in ("free",):
        raise HTTPException(status_code=400, detail="Solo aplica a usuarios con plan free")

    # Set expiry in the past → expiration job will suspend on next run
    past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    _user_repo.update_plan(user_id, "free", past)
    _hosting_repo.log_orchestrator_event(
        container_name="—",
        user_id=user_id,
        event_type="PLAN_DEACTIVATED",
        message=f"Admin {admin['email']} desactivó el plan free del usuario. Expira en el próximo ciclo del job.",
    )
    return {"ok": True, "plan_expires_at": past, "note": "El contenedor se suspenderá en el próximo ciclo del job de expiración"}


@router.post("/users/{user_id}/plan/upgrade")
async def admin_upgrade_plan(
    user_id: int,
    body: UpgradePlanBody,
    request: Request,
    admin: dict = Depends(require_role("admin")),
):
    """Upgrade a user to a paid plan. Updates user plan, all their free hostings, and Docker resources."""
    if body.plan not in _VALID_PAID_PLANS:
        raise HTTPException(status_code=400, detail=f"Plan inválido. Opciones: {', '.join(_VALID_PAID_PLANS)}")

    user = _user_repo.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    resources = _PLAN_RESOURCES[body.plan]

    # 1. Update user plan record (clear plan_expires_at — paid plans don't expire)
    _user_repo.update_plan(user_id, body.plan, None)

    # 2. Update all their hostings and apply Docker resource limits
    hostings = _hosting_repo.get_user_hostings(user_id)
    docker_errors = []
    for h in hostings:
        _hosting_repo.update_hosting_plan(h["hosting_id"], body.plan)
        if h.get("status") in ("active", "starting"):
            result = await _run_docker(
                "docker", "update",
                "--cpus", resources["cpu"],
                "--memory", resources["memory"],
                "--memory-swap", resources["memory"],  # disable swap
                h["container_name"],
                timeout=10,
            )
            if result.returncode != 0:
                err = result.stderr.strip()
                docker_errors.append({"container": h["container_name"], "error": err})

    _hosting_repo.log_orchestrator_event(
        container_name="—",
        user_id=user_id,
        event_type="PLAN_UPGRADED",
        message=(
            f"Admin {admin['email']} actualizó el plan a '{body.plan}'. "
            f"CPU: {resources['cpu']}, RAM: {resources['memory']}. "
            f"Hostings afectados: {len(hostings)}."
        ),
    )
    return {
        "ok": True,
        "plan": body.plan,
        "hostings_updated": len(hostings),
        "docker_errors": docker_errors,
    }
