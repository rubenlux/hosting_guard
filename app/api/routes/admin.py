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

    container    = hosting["container_name"]
    db_container = container.replace("_wp_", "_db_", 1) if "_wp_" in container else None
    targets      = [container] + ([db_container] if db_container else [])

    # 1. Remove containers; log Docker errors but don't abort on "No such container"
    docker_errors = []
    for cname in targets:
        r = await _run_docker("docker", "rm", "-f", cname, timeout=15)
        if r.returncode != 0 and "No such container" not in (r.stderr or ""):
            docker_errors.append(f"{cname}: {(r.stderr or '').strip()[:120]}")

    # 2. Audit log BEFORE modifying DB
    _hosting_repo.log_orchestrator_event(
        container, hosting["user_id"],
        "admin_terminate",
        f"TERMINADO por admin {admin['email']} | Razón: {reason} | IP: {_get_ip(request)}"
        + (f" | docker_errors: {docker_errors}" if docker_errors else ""),
    )

    # 3. Soft-delete (preserves audit trail, cleans metrics)
    _hosting_repo.soft_delete_hosting(hosting_id, db_container=db_container)

    return {
        "ok": True,
        "terminated": hosting_id,
        "container": container,
        "reason": reason,
        "admin": admin["email"],
        "docker_errors": docker_errors,
        "at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/metrics/node")
def get_node_metrics(_: dict = Depends(require_role("admin"))):
    """Real node metrics from Prometheus. Forecast includes confidence scoring."""
    import re
    import os
    import subprocess
    import requests as _req
    from app.infra.db import get_connection, release_connection

    PROM = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
    _FS = 'fstype!~"tmpfs|overlay",mountpoint="/"'

    QUERIES = {
        "cpu_pct":  '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[2m])) * 100)',
        "ram_pct":  "(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100",
        "disk_pct": f'(1 - node_filesystem_avail_bytes{{{_FS}}} / node_filesystem_size_bytes{{{_FS}}}) * 100',
        "disk_avail_bytes": f'node_filesystem_avail_bytes{{{_FS}}}',
        "disk_total_bytes": f'node_filesystem_size_bytes{{{_FS}}}',
        # Use 24h window for forecast to avoid single-event distortion
        "disk_avail_predicted": f'predict_linear(node_filesystem_avail_bytes{{{_FS}}}[24h], 86400*14)',
        "disk_deriv_24h":       f'deriv(node_filesystem_avail_bytes{{{_FS}}}[24h])',
        # Variance check: stddev/avg over 6h — detects builds, imports, prune spikes
        "disk_stddev_6h": f'stddev_over_time(node_filesystem_avail_bytes{{{_FS}}}[6h])',
        "disk_avg_6h":    f'avg_over_time(node_filesystem_avail_bytes{{{_FS}}}[6h])',
        # History check: how many samples in last 24h (node-exporter scrapes every 15s → ~5760/day)
        "disk_samples_24h": f'count_over_time(node_filesystem_avail_bytes{{{_FS}}}[24h])',
        "ram_avail_predicted": "predict_linear(node_memory_MemAvailable_bytes[24h], 86400*14)",
        "ram_avail_bytes":     "node_memory_MemAvailable_bytes",
        "ram_total_bytes":     "node_memory_MemTotal_bytes",
        "cpu_idle_predicted":  "predict_linear(avg_over_time(avg(rate(node_cpu_seconds_total{mode='idle'}[5m]))[24h:5m]), 86400*14)",
        "docker_p95": "histogram_quantile(0.95, rate(hosting_guard_docker_op_duration_seconds_bucket[5m]))",
    }

    result = {"source": "prometheus", "available": False}

    def _query(q: str):
        try:
            resp = _req.get(f"{PROM}/api/v1/query", params={"query": q}, timeout=5)
            resp.raise_for_status()
            series = resp.json().get("data", {}).get("result", [])
            return float(series[0]["value"][1]) if series else None
        except Exception:
            return None

    def _parse_docker_size(s: str):
        """'1.8GB' or '1.8 GB (56%)' → bytes as int, or None."""
        m = re.match(r"([\d.]+)\s*(B|kB|KB|MB|GB|TB)", s.replace(",", "."))
        if not m:
            return None
        val, unit = float(m.group(1)), m.group(2).upper()
        mult = {"B": 1, "KB": 1000, "MB": 1_000_000, "GB": 1_000_000_000, "TB": 1_000_000_000_000}
        return int(val * mult.get(unit, 1))

    def _fmt_bytes(n):
        if n is None:
            return None
        for unit, div in (("GB", 1e9), ("MB", 1e6), ("KB", 1e3)):
            if n >= div:
                return f"{n / div:.1f} {unit}"
        return f"{n} B"

    def _get_docker_reclaimable():
        """Parse docker system df text output. Returns dict or None on failure."""
        try:
            r = subprocess.run(
                ["docker", "system", "df"], capture_output=True, text=True, timeout=15
            )
            if r.returncode != 0:
                return None
            lines = r.stdout.strip().splitlines()
            out = {}
            for line in lines[1:]:
                parts = line.split()
                if not parts:
                    continue
                if parts[0] == "Images" and len(parts) >= 5:
                    out["images_total_str"]       = parts[3]
                    out["images_reclaimable_str"] = parts[4].split("(")[0].strip()
                    out["images_reclaimable_bytes"] = _parse_docker_size(out["images_reclaimable_str"])
                elif parts[0] == "Build" and len(parts) >= 6:
                    out["build_cache_str"]         = parts[5].split("(")[0].strip()
                    out["build_cache_bytes"]       = _parse_docker_size(out["build_cache_str"])
                elif parts[0] == "Local" and len(parts) >= 6:
                    out["volumes_reclaimable_str"] = parts[5].split("(")[0].strip()
                    out["volumes_reclaimable_bytes"] = _parse_docker_size(out["volumes_reclaimable_str"])
            return out if out else None
        except Exception:
            return None

    def _check_forecast_confidence():
        """
        Returns (confidence, reason).
        confidence: "high" | "low" | "unavailable"
        Checks:
          1. Enough Prometheus history (≥24h of samples)
          2. Low disk variance in last 6h (no builds/imports distorting trend)
          3. No import events in orchestrator_events in last 6h
        """
        confidence = "high"
        reason = None

        # 1. History check
        samples = _query(QUERIES["disk_samples_24h"])
        if samples is not None and samples < 200:
            return "unavailable", "Historial insuficiente — se necesitan al menos 24h de datos"

        # 2. Variance check: coefficient of variation > 1.5% = unstable window
        stddev = _query(QUERIES["disk_stddev_6h"])
        avg6h  = _query(QUERIES["disk_avg_6h"])
        if stddev is not None and avg6h and avg6h > 0:
            cov = stddev / avg6h
            if cov > 0.015:
                confidence = "low"
                reason = "Alta varianza en disco en las últimas 6h — posible build, import o docker prune reciente"

        # 3. Recent imports in DB
        if confidence == "high":
            try:
                conn2 = get_connection()
                try:
                    c2 = conn2.cursor()
                    c2.execute(
                        """
                        SELECT COUNT(*) AS cnt FROM orchestrator_events
                        WHERE event_type IN ('import_start', 'import_completed', 'import_failed')
                          AND created_at::timestamptz > NOW() - INTERVAL '6 hours'
                        """
                    )
                    row = c2.fetchone()
                    n = (row["cnt"] if hasattr(row, "__getitem__") else row[0]) if row else 0
                    if n > 0:
                        confidence = "low"
                        reason = f"Se detectó importación reciente ({n} evento(s) en las últimas 6h) — el crecimiento de disco puede ser temporal"
                finally:
                    release_connection(conn2)
            except Exception:
                pass

        return confidence, reason

    try:
        cpu  = _query(QUERIES["cpu_pct"])
        ram  = _query(QUERIES["ram_pct"])
        disk = _query(QUERIES["disk_pct"])

        if cpu is None and ram is None and disk is None:
            return result

        avail_now = _query(QUERIES["disk_avail_bytes"])
        total     = _query(QUERIES["disk_total_bytes"])

        # Disk growth: use 24h deriv instead of 6h to smooth single-event spikes
        disk_deriv = _query(QUERIES["disk_deriv_24h"])
        disk_growth_pct_per_day = None
        days_left = None

        if total and total > 0:
            if disk_deriv is not None:
                disk_growth_pct_per_day = round(-disk_deriv * 86400 / total * 100, 2)
            avail_predicted = _query(QUERIES["disk_avail_predicted"])
            if avail_predicted is not None and avail_now is not None:
                if avail_predicted <= 0:
                    growth_rate = (avail_now - avail_predicted) / (14 * 86400)
                    if growth_rate > 0:
                        days_left = round(avail_now / growth_rate / 86400, 1)
                elif disk_deriv is not None and disk_deriv < 0:
                    fill_rate = -disk_deriv
                    if fill_rate > 0:
                        days_left = round(avail_now / fill_rate / 86400, 1)

        # CPU forecast
        cpu_days_left = None
        cpu_idle_predicted = _query(QUERIES["cpu_idle_predicted"])
        if cpu is not None and cpu_idle_predicted is not None:
            cpu_future = (1 - max(0.0, min(1.0, cpu_idle_predicted))) * 100
            if cpu_future >= 90:
                delta_per_day = (cpu_future - cpu) / 14
                if delta_per_day > 0:
                    cpu_days_left = round((90 - cpu) / delta_per_day, 1)

        # RAM forecast
        ram_days_left = None
        ram_avail_predicted = _query(QUERIES["ram_avail_predicted"])
        ram_avail_now       = _query(QUERIES["ram_avail_bytes"])
        ram_total           = _query(QUERIES["ram_total_bytes"])
        if ram_avail_predicted is not None and ram_avail_now is not None and ram_total and ram_total > 0:
            if ram_avail_predicted <= 0 and ram_avail_now > 0:
                fill_rate = (ram_avail_now - ram_avail_predicted) / (14 * 86400)
                if fill_rate > 0:
                    ram_days_left = round(ram_avail_now / fill_rate / 86400, 1)

        # Forecast confidence
        forecast_confidence, forecast_unavailable_reason = _check_forecast_confidence()
        # Suppress days_left projections when confidence is not high
        if forecast_confidence != "high":
            days_left = None

        # Docker reclaimable
        docker_reclaimable = _get_docker_reclaimable()
        if docker_reclaimable:
            for k in ("images_reclaimable_bytes", "build_cache_bytes", "volumes_reclaimable_bytes"):
                if k in docker_reclaimable and docker_reclaimable[k] is not None:
                    label = k.replace("_bytes", "_str") if k.replace("_bytes", "_str") not in docker_reclaimable else None
                    if label:
                        docker_reclaimable[label] = _fmt_bytes(docker_reclaimable[k])

        # Docker p95 latency
        docker_p95 = _query(QUERIES["docker_p95"])

        def _status(pct):
            if pct is None:  return "unknown"
            if pct >= 90:    return "critical"
            if pct >= 70:    return "warning"
            return "ok"

        statuses = [_status(cpu), _status(ram), _status(disk)]
        overall = (
            "critical" if "critical" in statuses
            else "warning" if "warning" in statuses
            else "ok"
        )

        result.update({
            "available":          True,
            "cpu_pct":            round(cpu,  1) if cpu  is not None else None,
            "ram_pct":            round(ram,  1) if ram  is not None else None,
            "disk_pct":           round(disk, 1) if disk is not None else None,
            "disk_days_left":          days_left,
            "disk_growth_pct_per_day": disk_growth_pct_per_day,
            "ram_days_left":           ram_days_left,
            "cpu_days_left":           cpu_days_left,
            "docker_p95_seconds":      round(docker_p95, 3) if docker_p95 is not None else None,
            "status":             overall,
            "recommendation":     {
                "ok":       "Capacidad normal — sin acción requerida",
                "warning":  "Revisar crecimiento — planificar escalado próximamente",
                "critical": "Escalar infraestructura ahora",
            }[overall],
            "cpu_status":         _status(cpu),
            "ram_status":         _status(ram),
            "disk_status":        _status(disk),
            # Forecast confidence
            "forecast_confidence":          forecast_confidence,
            "forecast_unavailable_reason":  forecast_unavailable_reason,
            # Docker storage breakdown
            "docker_reclaimable": docker_reclaimable,
        })
    except Exception as exc:
        result["error"] = str(exc)

    return result


@router.get("/metrics/tenants")
def get_tenant_resource_usage(_: dict = Depends(require_role("admin"))):
    """Top tenants by CPU/RAM from recent orchestrator events."""
    from app.infra.db import get_connection, release_connection
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # Average cpu/mem — use 2h window for current health; fall back to 24h if empty
        _TENANT_QUERY = """
            SELECT
                o.container_name,
                o.user_id,
                u.email,
                u.plan,
                u.balance,
                AVG(o.cpu_pct)  AS avg_cpu,
                AVG(o.mem_pct)  AS avg_mem,
                MAX(o.created_at) AS last_seen
            FROM orchestrator_events o
            JOIN users u ON u.user_id = o.user_id
            JOIN hostings h ON h.container_name = o.container_name
            WHERE o.cpu_pct IS NOT NULL
              AND o.created_at::timestamptz > NOW() - INTERVAL %s
              AND h.status NOT IN ('deleted', 'terminated')
            GROUP BY o.container_name, o.user_id, u.email, u.plan, u.balance
            ORDER BY avg_cpu DESC
            LIMIT 10
        """
        cursor.execute(_TENANT_QUERY, ("2 hours",))
        rows = cursor.fetchall()
        window = "2h"
        if not rows:
            cursor.execute(_TENANT_QUERY, ("24 hours",))
            rows = cursor.fetchall()
            window = "24h"
        COST_PER_CONTAINER_MONTHLY = float(os.getenv("COST_PER_CONTAINER_MONTHLY", "5.0"))
        tenants = []
        for r in rows:
            avg_cpu = round(r["avg_cpu"] or 0, 1)
            avg_mem = round(r["avg_mem"] or 0, 1)
            balance = r["balance"] or 0
            plan = r["plan"] or "free"
            abusing = avg_cpu > 60 or avg_mem > 70
            costly  = abusing and balance < 5 and plan == "free"
            monthly_cost = round(COST_PER_CONTAINER_MONTHLY, 2)
            at_loss = balance < monthly_cost and plan == "free"
            tenants.append({
                "container_name":      r["container_name"],
                "user_id":             r["user_id"],
                "email":               r["email"],
                "plan":                plan,
                "balance":             round(balance, 2),
                "avg_cpu":             avg_cpu,
                "avg_mem":             avg_mem,
                "last_seen":           r["last_seen"],
                "abusing":             abusing,
                "costly":              costly,
                "monthly_cost_usd":    monthly_cost,
                "at_loss":             at_loss,
            })
        return {"tenants": tenants, "window": window, "cost_per_container_usd": COST_PER_CONTAINER_MONTHLY}
    except Exception as exc:
        return {"tenants": [], "error": str(exc)}
    finally:
        release_connection(conn)


_JOB_STALE_MINUTES = {
    "reconcile":   10,
    "expire":      780,   # 13h
    "health_check": 10,
    "traffic":     10,
}

@router.get("/jobs/summary")
def get_jobs_summary(_: dict = Depends(require_role("admin"))):
    """Last run times, run counts, and explicit status for background jobs."""
    from app.infra.db import get_connection, release_connection
    import os, requests as _req
    conn = get_connection()
    try:
        cursor = conn.cursor()
        jobs = {}
        now = datetime.now(timezone.utc)
        for event_type in ("reconcile", "expire", "health_check", "traffic"):
            # Count in last 24h and get the most recent run ever
            cursor.execute("""
                SELECT COUNT(*) AS cnt_24h,
                       MAX(created_at) AS last_run
                FROM orchestrator_events
                WHERE event_type ILIKE %s
            """, (f"%{event_type}%",))
            row = cursor.fetchone()
            cnt_24h = int(row["cnt_24h"]) if row else 0
            last_run = row["last_run"] if row else None

            # Determine status
            if last_run is None:
                status = "never_run"
            else:
                if last_run.tzinfo is None:
                    last_run = last_run.replace(tzinfo=timezone.utc)
                mins_ago = (now - last_run).total_seconds() / 60
                stale_after = _JOB_STALE_MINUTES.get(event_type, 30)
                status = "stale" if mins_ago > stale_after else "ok"

            jobs[event_type] = {
                "count_24h":          cnt_24h,
                "last_run":           last_run.isoformat() if last_run else None,
                "status":             status,
            }

        # Prometheus: db_errors_total
        PROM = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
        db_errors = None
        try:
            resp = _req.get(f"{PROM}/api/v1/query",
                            params={"query": "rate(hosting_guard_db_errors_total[1h])"},
                            timeout=4)
            series = resp.json().get("data", {}).get("result", [])
            if series:
                db_errors = round(float(series[0]["value"][1]) * 3600, 2)
        except Exception:
            pass

        return {"jobs": jobs, "db_errors_last_hour": db_errors}
    except Exception as exc:
        return {"jobs": {}, "error": str(exc)}
    finally:
        release_connection(conn)


@router.get("/metrics/unit-economics")
def get_unit_economics(_: dict = Depends(require_role("admin"))):
    """
    Per-tenant unit economics: infra cost vs revenue.

    Costs are proportional allocations of the monthly server bill,
    weighted by each tenant's CPU / RAM / Disk share.
    Revenue is the tenant's recorded balance (or plan price if set).
    """
    import os, requests as _req
    from app.infra.db import get_connection, release_connection

    SERVER_COST_MONTHLY = float(os.getenv("SERVER_COST_MONTHLY", "20.0"))
    # Total node capacity (configurable or auto-detected from Prometheus)
    PROM = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")

    def _prom(q):
        try:
            r = _req.get(f"{PROM}/api/v1/query", params={"query": q}, timeout=5)
            s = r.json().get("data", {}).get("result", [])
            return float(s[0]["value"][1]) if s else None
        except Exception:
            return None

    # Node totals from Prometheus
    total_ram_bytes  = _prom("node_memory_MemTotal_bytes") or 0
    total_disk_bytes = _prom('node_filesystem_size_bytes{fstype!~"tmpfs|overlay",mountpoint="/"}') or 0
    cpu_cores        = _prom("count(node_cpu_seconds_total{mode='idle'})") or float(os.getenv("NODE_CPU_CORES", "2"))
    total_ram_mb     = total_ram_bytes / 1024 / 1024 if total_ram_bytes else float(os.getenv("NODE_RAM_MB", "4096"))
    total_disk_mb    = total_disk_bytes / 1024 / 1024 if total_disk_bytes else float(os.getenv("NODE_DISK_MB", "80000"))

    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Get active hostings joined with user data
        cursor.execute("""
            SELECT
                h.hosting_id,
                h.container_name,
                h.plan,
                h.user_id,
                u.email,
                u.balance,
                o.avg_cpu,
                o.avg_mem
            FROM hostings h
            JOIN users u ON u.user_id = h.user_id
            LEFT JOIN (
                SELECT container_name,
                       AVG(cpu_pct) AS avg_cpu,
                       AVG(mem_pct) AS avg_mem
                FROM orchestrator_events
                WHERE cpu_pct IS NOT NULL
                  AND created_at::timestamptz > NOW() - INTERVAL '24 hours'
                GROUP BY container_name
            ) o ON o.container_name = h.container_name
            WHERE h.status = 'active'
        """)
        rows = cursor.fetchall()
    except Exception as exc:
        return {"error": str(exc), "tenants": []}
    finally:
        release_connection(conn)

    # Plan monthly revenue estimates (override with real payments when available)
    PLAN_REVENUE = {
        "free":     0.0,
        "personal": 9.0,
        "negocio":  19.0,
        "agencia":  39.0,
    }

    tenants = []
    total_cpu_used = total_ram_used = total_disk_used = 0.0

    for r in rows:
        avg_cpu = r["avg_cpu"] or 0.0
        avg_mem = r["avg_mem"] or 0.0  # % of container RAM allocation

        # Approximate per-container resource usage in absolute units
        cpu_used  = (avg_cpu / 100) * cpu_cores          # fractional cores
        ram_used  = (avg_mem / 100) * (total_ram_mb / max(len(rows), 1))   # MB (fair-share estimate)
        disk_used = 500.0  # default 500MB per container (no per-container disk metric yet)

        total_cpu_used  += cpu_used
        total_ram_used  += ram_used
        total_disk_used += disk_used

        tenants.append({
            "container_name": r["container_name"],
            "user_id":        r["user_id"],
            "email":          r["email"],
            "plan":           r["plan"] or "free",
            "balance":        round(r["balance"] or 0, 2),
            "avg_cpu_pct":    round(avg_cpu, 1),
            "avg_mem_pct":    round(avg_mem, 1),
            "_cpu_used":      cpu_used,
            "_ram_used":      ram_used,
            "_disk_used":     disk_used,
        })

    # Second pass: allocate costs proportionally across all active tenants
    total_allocated_cpu  = max(total_cpu_used, 0.001)
    total_allocated_ram  = max(total_ram_used, 0.001)
    total_allocated_disk = max(total_disk_used, 0.001)

    # Cost weight: 50% CPU, 35% RAM, 15% Disk
    CPU_W, RAM_W, DISK_W = 0.50, 0.35, 0.15

    result_tenants = []
    agg_revenue = agg_cost = 0.0

    for t in tenants:
        plan = t["plan"]
        revenue = PLAN_REVENUE.get(plan, 0.0)

        cpu_cost  = (t["_cpu_used"]  / total_allocated_cpu)  * SERVER_COST_MONTHLY * CPU_W
        ram_cost  = (t["_ram_used"]  / total_allocated_ram)  * SERVER_COST_MONTHLY * RAM_W
        disk_cost = (t["_disk_used"] / total_allocated_disk) * SERVER_COST_MONTHLY * DISK_W
        infra_cost = round(cpu_cost + ram_cost + disk_cost, 2)

        profit = round(revenue - infra_cost, 2)
        margin_pct = round(profit / revenue * 100, 1) if revenue > 0 else None

        if revenue == 0:
            status = "loss"
        elif profit < 0:
            status = "loss"
        elif profit < revenue * 0.1:
            status = "break_even"
        else:
            status = "profitable"

        upgrade_candidate = plan == "free" and (t["avg_cpu_pct"] > 40 or t["avg_mem_pct"] > 50)

        agg_revenue += revenue
        agg_cost    += infra_cost

        result_tenants.append({
            "container_name":    t["container_name"],
            "user_id":           t["user_id"],
            "email":             t["email"],
            "plan":              plan,
            "balance":           t["balance"],
            "avg_cpu_pct":       t["avg_cpu_pct"],
            "avg_mem_pct":       t["avg_mem_pct"],
            "revenue":           round(revenue, 2),
            "infra_cost":        infra_cost,
            "profit":            profit,
            "margin_pct":        margin_pct,
            "status":            status,
            "upgrade_candidate": upgrade_candidate,
        })

    # Sort by profit ascending (worst first)
    result_tenants.sort(key=lambda x: x["profit"])

    total_profit = round(agg_revenue - agg_cost, 2)
    avg_margin = round(total_profit / agg_revenue * 100, 1) if agg_revenue > 0 else None

    return {
        "tenants": result_tenants,
        "summary": {
            "server_cost_monthly": SERVER_COST_MONTHLY,
            "total_revenue":       round(agg_revenue, 2),
            "total_infra_cost":    round(agg_cost, 2),
            "total_profit":        total_profit,
            "avg_margin_pct":      avg_margin,
            "active_containers":   len(result_tenants),
        },
        "node": {
            "cpu_cores":    cpu_cores,
            "total_ram_mb": round(total_ram_mb),
            "total_disk_mb": round(total_disk_mb),
        },
    }


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

    containers_today = users_today = 0
    try:
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) AS cnt FROM hostings WHERE created_at::timestamptz > NOW() - INTERVAL '24 hours'")
            row = cursor.fetchone()
            containers_today = int(row["cnt"]) if row else 0
            cursor.execute("SELECT COUNT(*) AS cnt FROM users WHERE created_at::timestamptz > NOW() - INTERVAL '24 hours'")
            row = cursor.fetchone()
            users_today = int(row["cnt"]) if row else 0
        finally:
            release_connection(conn)
    except Exception:
        pass

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
        "growth": {
            "containers_today": containers_today,
            "users_today": users_today,
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


@router.get("/metrics/containers/history")
def get_container_history(_: dict = Depends(require_role("admin"))):
    """Per-container CPU%/RAM% time series (last 2h) from orchestrator_events."""
    from app.infra.db import get_connection, release_connection
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                o.container_name,
                u.email,
                u.plan,
                DATE_TRUNC('minute', o.created_at::timestamptz) AS minute,
                AVG(o.cpu_pct) AS avg_cpu,
                AVG(o.mem_pct) AS avg_ram
            FROM orchestrator_events o
            JOIN users u ON u.user_id = o.user_id
            JOIN hostings h ON h.container_name = o.container_name
            WHERE o.cpu_pct IS NOT NULL
              AND o.created_at::timestamptz > NOW() - INTERVAL '2 hours'
              AND h.status NOT IN ('deleted', 'terminated')
            GROUP BY o.container_name, u.email, u.plan, minute
            ORDER BY o.container_name, minute
        """)
        rows = cursor.fetchall()

        containers: dict = {}
        for row in rows:
            name = row["container_name"]
            if name not in containers:
                containers[name] = {"email": row["email"], "plan": row["plan"], "data": []}
            containers[name]["data"].append({
                "t": row["minute"].strftime("%H:%M"),
                "cpu": round(float(row["avg_cpu"] or 0), 1),
                "ram": round(float(row["avg_ram"] or 0), 1),
            })

        return {"available": bool(containers), "containers": containers, "window_minutes": 120}
    finally:
        release_connection(conn)


@router.post("/hostings/{hosting_id}/force-cleanup")
async def admin_force_cleanup(
    hosting_id: int,
    request: Request,
    admin: dict = Depends(require_role("admin")),
):
    """
    Force cleanup for orphaned hostings (containers alive but DB record stuck).

    Differences from normal delete:
    - Tolerates 'No such container' (already gone = ok)
    - Always soft-deletes the DB record regardless of Docker outcome
    - Does NOT abort if containers can't be found — logs the discrepancy instead
    """
    hosting = _hosting_repo.get_hosting_any(hosting_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting no encontrado")

    container    = hosting["container_name"]
    db_container = container.replace("_wp_", "_db_", 1) if "_wp_" in container else None
    targets      = [container] + ([db_container] if db_container else [])

    removed  = []
    not_found = []
    errors   = []

    for cname in targets:
        r = await _run_docker("docker", "rm", "-f", cname, timeout=15)
        err = (r.stderr or "").strip()
        if r.returncode == 0:
            removed.append(cname)
        elif "No such container" in err:
            not_found.append(cname)
        else:
            errors.append(f"{cname}: {err[:120]}")

    # Always clean DB — force cleanup overrides the normal safety gate
    _hosting_repo.soft_delete_hosting(hosting_id, db_container=db_container)

    _hosting_repo.log_orchestrator_event(
        container, hosting["user_id"],
        "admin_force_cleanup",
        f"Force cleanup por {admin['email']} desde {_get_ip(request)} | "
        f"removed={removed} not_found={not_found} errors={errors}",
    )

    return {
        "ok": True,
        "hosting_id": hosting_id,
        "removed": removed,
        "not_found": not_found,
        "docker_errors": errors,
        "admin": admin["email"],
        "at": datetime.now(timezone.utc).isoformat(),
    }
