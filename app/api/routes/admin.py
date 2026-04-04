import asyncio
import subprocess
from fastapi import APIRouter, Depends, HTTPException
from app.api.security import require_role
from app.infra.audit.user_repository import UserRepository
from app.infra.audit.hosting_repository import HostingRepository
from app.infra.audit.pixel_repository import PixelRepository
from app.infra.audit.metrics_repository import MetricsRepository
from app.infra.audit.sqlite import get_connection

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
    result = await _run_docker(
        "docker", "stats", "--no-stream",
        "--format", "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.MemPerc}}|{{.NetIO}}",
        timeout=15,
    )

    docker_stats = {}
    if result.returncode == 0:
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
    decision_events = [
        dict(r) for r in conn.execute(
            "SELECT event_id, timestamp, overall_status, confidence_level, requires_human_attention "
            "FROM decision_events WHERE tenant_id = ? ORDER BY timestamp DESC LIMIT 20",
            (tenant_id,)
        ).fetchall()
    ]
    execution_events = [
        dict(r) for r in conn.execute(
            "SELECT execution_id, timestamp, action_type, status "
            "FROM execution_events WHERE tenant_id = ? ORDER BY timestamp DESC LIMIT 20",
            (tenant_id,)
        ).fetchall()
    ]
    human_events = [
        dict(r) for r in conn.execute(
            "SELECT action_event_id, timestamp, action_type, actor, reason "
            "FROM human_action_events WHERE tenant_id = ? ORDER BY timestamp DESC LIMIT 20",
            (tenant_id,)
        ).fetchall()
    ]

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
    conn = get_connection()
    rows = conn.cursor().execute(
        "SELECT oe.event_id, oe.container_name, oe.user_id, oe.event_type, oe.message, oe.created_at, "
        "u.email FROM orchestrator_events oe "
        "LEFT JOIN users u ON oe.user_id = u.user_id "
        "ORDER BY oe.created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


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
