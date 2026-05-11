import asyncio
import logging
import subprocess
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)
from pathlib import Path
from typing import Optional, Literal, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import os
from app.api.rate_limit import limiter
from app.api.security import require_role
from app.infra.audit.user_repository import UserRepository
from app.infra.audit.hosting_repository import HostingRepository
from app.infra.audit.pixel_repository import PixelRepository
from app.infra.audit.metrics_repository import MetricsRepository
from app.infra.audit.repository import AuditRepository
from app.infra.audit.admin_audit_repository import AdminAuditRepository
from app.infra.audit.notification_repository import NotificationRepository

router = APIRouter(prefix="/admin", tags=["admin"])

_user_repo    = UserRepository()
_hosting_repo = HostingRepository()
_audit_repo   = AuditRepository()
_pixel_repo   = PixelRepository()
_metrics_repo = MetricsRepository()
_admin_audit  = AdminAuditRepository()
_notif_repo   = NotificationRepository()


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


@router.get("/report")
@limiter.limit("4/hour")
async def get_admin_report(request: Request, _: dict = Depends(require_role("admin"))):
    """On-demand AI platform intelligence report (same as the daily email)."""
    from app.services.admin_ai_reporter import generate_platform_report
    try:
        report = await generate_platform_report()
        return {"ok": True, "report": report}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/users")
def list_all_users(user: dict = Depends(require_role("admin"))):
    return _user_repo.get_all_users()


@router.get("/hostings")
def list_all_hostings(user: dict = Depends(require_role("admin"))):
    return _hosting_repo.get_all_hostings()


@router.get("/hostings/metrics")
@limiter.limit("5/minute")
async def get_all_hostings_metrics(request: Request, _: dict = Depends(require_role("admin"))):
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
def get_user_full(user_id: int, request: Request, admin: dict = Depends(require_role("admin"))):
    profile = _user_repo.get_user_by_id(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    for _sensitive in ("password_hash", "totp_secret", "totp_backup_codes"):
        profile.pop(_sensitive, None)
    try:
        from app.services.activity_service import log_event as _log
        _log(user_id=admin["user_id"], actor_type="admin", actor_email=admin.get("email"),
             event_type="admin_viewed_user", category="admin", severity="info",
             title=f"Admin vio perfil de {profile.get('email', user_id)}",
             ip=_get_ip(request), source="admin",
             metadata={"target_user_id": user_id, "target_email": profile.get("email")})
    except Exception:
        pass

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


@router.get("/users/online")
def get_online_users(admin: dict = Depends(require_role("admin"))):
    """Return presence summary + unique users (grouped) with their sessions."""
    from app.infra.audit.session_repository import get_presence_summary, get_grouped_users
    from app.services.activity_service import mask_ip
    from datetime import datetime, timezone

    summary = get_presence_summary()
    raw_users = get_grouped_users()

    now = datetime.now(timezone.utc)
    users = []
    for u in raw_users:
        last = u.get("last_seen")
        if last:
            diff = now - last if last.tzinfo else now - last.replace(tzinfo=timezone.utc)
            delta_s = diff.total_seconds()
        else:
            delta_s = 9999

        if delta_s <= 120:
            status = "online"
        elif delta_s <= 900:
            status = "active"
        else:
            status = "idle"

        sessions = [
            {
                **s,
                "ip":     mask_ip(s.get("ip")),
                "device": _parse_device(s.get("user_agent") or ""),
            }
            for s in u.get("sessions", [])
        ]

        users.append({
            "user_id":            u["user_id"],
            "email":              u["email"],
            "plan":               u.get("plan", "free"),
            "role":               u.get("role", "user"),
            "subscription_status": u.get("subscription_status"),
            "status":             status,
            "last_seen":          u.get("last_seen"),
            "current_path":       u.get("current_path"),
            "ip":                 mask_ip(u.get("ip")),
            "device":             _parse_device(u.get("user_agent") or ""),
            "session_count":      len(sessions),
            "sessions":           sessions,
        })

    # keep "sessions" key for any existing callers
    return {**summary, "users": users, "sessions": users}


def _parse_device(ua: str) -> str:
    ua_l = ua.lower()
    if "mobile" in ua_l or "android" in ua_l or "iphone" in ua_l:
        browser = "Chrome Mobile" if "chrome" in ua_l else "Mobile Browser"
    elif "windows" in ua_l:
        browser = "Chrome/Win" if "chrome" in ua_l else ("Firefox/Win" if "firefox" in ua_l else "Windows")
    elif "mac" in ua_l:
        browser = "Chrome/Mac" if "chrome" in ua_l else ("Safari" if "safari" in ua_l else "Mac")
    elif "linux" in ua_l:
        browser = "Linux Browser"
    else:
        browser = "Unknown"
    return browser


@router.get("/activity")
def get_activity_log(
    user_id: Optional[int] = None,
    hosting_id: Optional[int] = None,
    category: Optional[str] = None,
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    source: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    admin: dict = Depends(require_role("admin")),
):
    """Admin activity timeline — full access, IPs masked by default."""
    from app.services.activity_service import query_events, mask_ip

    events = query_events(
        user_id=user_id,
        hosting_id=hosting_id,
        category=category,
        event_type=event_type,
        severity=severity,
        source=source,
        date_from=date_from,
        date_to=date_to,
        limit=min(limit, 500),
        offset=offset,
    )
    for e in events:
        e["ip"] = mask_ip(e.get("ip"))
    return {"items": events, "limit": limit, "offset": offset}


@router.get("/users/{user_id}/activity")
def get_user_activity(
    user_id: int,
    limit: int = 100,
    offset: int = 0,
    admin: dict = Depends(require_role("admin")),
):
    """Activity timeline for a specific user — for user detail / support view."""
    from app.services.activity_service import query_events, mask_ip

    events = query_events(user_id=user_id, limit=min(limit, 500), offset=offset)
    for e in events:
        e["ip"] = mask_ip(e.get("ip"))
    return {"items": events, "limit": limit, "offset": offset}


@router.get("/resources/overview")
def get_resources_overview(admin: dict = Depends(require_role("admin"))):
    """Latest resource snapshot aggregated across all active hostings."""
    from app.infra.db import get_connection, release_connection
    conn = get_connection()
    try:
        cur = conn.cursor()
        # Use the most recent sample window: start at the latest sampled_at minus 3×interval
        # so we never show empty if the scheduler is running (interval=60s → 3 min grace).
        # Hard floor at 10 minutes covers cold-start after a rebuild.
        cur.execute(
            """SELECT
                 COALESCE(
                   GREATEST(MAX(sampled_at) - INTERVAL '3 minutes', NOW() - INTERVAL '10 minutes'),
                   NOW() - INTERVAL '10 minutes'
                 ) AS since
               FROM hosting_resource_samples"""
        )
        _since_row = cur.fetchone()
        since = _since_row["since"] if _since_row else None

        cur.execute(
            """SELECT
                 COUNT(DISTINCT s.hosting_id)                         AS total_hostings,
                 ROUND(AVG(s.cpu_pct)::numeric, 1)                   AS avg_cpu_pct,
                 ROUND(MAX(s.cpu_pct)::numeric, 1)                   AS max_cpu_pct,
                 ROUND(AVG(s.mem_mb)::numeric, 0)                    AS avg_mem_mb,
                 ROUND(SUM(s.mem_mb)::numeric, 0)                    AS total_mem_mb,
                 ROUND(MAX(s.mem_mb)::numeric, 0)                    AS max_mem_mb,
                 MAX(s.sampled_at)                                    AS last_sample_at
               FROM hosting_resource_samples s
               WHERE s.sampled_at >= %s""",
            (since,),
        )
        row = dict(cur.fetchone() or {})

        # Top 5 by CPU — same adaptive window
        cur.execute(
            """SELECT DISTINCT ON (s.hosting_id)
                 s.hosting_id, h.name, s.container_name,
                 s.cpu_pct, s.mem_mb, s.mem_limit_mb, s.sampled_at
               FROM hosting_resource_samples s
               JOIN hostings h USING (hosting_id)
               WHERE s.sampled_at >= %s
               ORDER BY s.hosting_id, s.sampled_at DESC""",
            (since,),
        )
        all_snaps = [dict(r) for r in cur.fetchall()]
        top_cpu = sorted(all_snaps, key=lambda x: x.get("cpu_pct") or 0, reverse=True)[:5]
        top_mem = sorted(all_snaps, key=lambda x: x.get("mem_mb") or 0, reverse=True)[:5]

        # Expose total row count so frontend can distinguish "table empty" from "stale data"
        cur.execute("SELECT COUNT(*) AS cnt, MAX(sampled_at) AS latest FROM hosting_resource_samples")
        _meta = dict(cur.fetchone() or {})

        return {
            **row,
            "top_cpu": top_cpu,
            "top_mem": top_mem,
            "snapshot_count": len(all_snaps),
            "total_samples_in_db": _meta.get("cnt") or 0,
            "newest_sample_in_db": _meta.get("latest"),
        }
    finally:
        release_connection(conn)


@router.get("/resources/tenants")
def get_resources_tenants(admin: dict = Depends(require_role("admin"))):
    """Latest resource snapshot per hosting, enriched with traffic, uptime, backup and restart data."""
    from app.infra.db import get_connection, release_connection
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT DISTINCT ON (s.hosting_id)
                 s.hosting_id, h.name, h.subdomain, h.status,
                 u.email AS user_email, u.plan,
                 s.container_name, s.cpu_pct, s.mem_mb, s.mem_limit_mb,
                 s.net_rx_mb, s.net_tx_mb,
                 COALESCE(s.disk_mb, NULL)              AS disk_mb,
                 s.sampled_at,
                 -- CPU 5-min stats from recent samples
                 cpu5.cpu_avg_5min, cpu5.cpu_max_5min,
                 -- Traffic last 24 h
                 ts.requests_24h, ts.errors_4xx_24h, ts.errors_5xx_24h,
                 -- Avg response time
                 uc.avg_response_ms,
                 -- Backup storage (all completed backups)
                 COALESCE(bs.backup_mb, 0)              AS backup_storage_mb,
                 -- Restarts last 24 h
                 COALESCE(rc.restart_count, 0)          AS restart_count_24h
               FROM hosting_resource_samples s
               JOIN hostings h USING (hosting_id)
               JOIN users u ON u.user_id = h.user_id
               LEFT JOIN LATERAL (
                   SELECT
                       ROUND(AVG(cpu_pct)::numeric, 1) AS cpu_avg_5min,
                       ROUND(MAX(cpu_pct)::numeric, 1) AS cpu_max_5min
                   FROM hosting_resource_samples
                   WHERE hosting_id = s.hosting_id
                     AND sampled_at >= NOW() - INTERVAL '5 minutes'
               ) cpu5 ON TRUE
               LEFT JOIN LATERAL (
                   SELECT
                       COALESCE(SUM(total_requests), 0) AS requests_24h,
                       COALESCE(SUM(errors_4xx), 0)     AS errors_4xx_24h,
                       COALESCE(SUM(errors_5xx), 0)     AS errors_5xx_24h
                   FROM traffic_stats
                   WHERE container_name = s.container_name
                     AND collected_at::TIMESTAMPTZ >= NOW() - INTERVAL '24 hours'
               ) ts ON TRUE
               LEFT JOIN LATERAL (
                   SELECT ROUND(AVG(response_ms)::numeric, 0)::float AS avg_response_ms
                   FROM uptime_checks
                   WHERE hosting_id = s.hosting_id
                     AND checked_at::TIMESTAMPTZ >= NOW() - INTERVAL '24 hours'
                     AND response_ms IS NOT NULL
               ) uc ON TRUE
               LEFT JOIN LATERAL (
                   SELECT COALESCE(SUM(size_bytes), 0) / 1048576.0 AS backup_mb
                   FROM backups
                   WHERE hosting_id = s.hosting_id AND status = 'completed'
               ) bs ON TRUE
               LEFT JOIN LATERAL (
                   SELECT COUNT(*) AS restart_count
                   FROM activity_events
                   WHERE hosting_id = s.hosting_id
                     AND event_type = 'hosting_restarted'
                     AND created_at::TIMESTAMPTZ >= NOW() - INTERVAL '24 hours'
               ) rc ON TRUE
               WHERE s.sampled_at >= (
                   SELECT COALESCE(
                     GREATEST(MAX(sampled_at) - INTERVAL '3 minutes', NOW() - INTERVAL '10 minutes'),
                     NOW() - INTERVAL '10 minutes'
                   ) FROM hosting_resource_samples
               )
               ORDER BY s.hosting_id, s.sampled_at DESC"""
        )
        rows = [dict(r) for r in cur.fetchall()]

        for r in rows:
            r["recommendation"] = _compute_recommendation(r)

        rows.sort(key=lambda x: x.get("cpu_pct") or 0, reverse=True)
        return {"items": rows, "count": len(rows)}
    finally:
        release_connection(conn)


def _compute_recommendation(r: dict) -> str:
    # Use 5-min average CPU to avoid false alarms from isolated spikes.
    # Fall back to current sample only when 5-min avg is not yet available.
    cpu  = r.get("cpu_avg_5min") or r.get("cpu_pct") or 0
    mem  = r.get("mem_mb") or 0
    lim  = r.get("mem_limit_mb") or 0
    e5xx = r.get("errors_5xx_24h") or 0
    rst  = r.get("restart_count_24h") or 0
    plan = r.get("plan", "free")
    mem_ratio = (mem / lim) if lim else 0

    if rst > 3 or e5xx > 20:
        return "revisar"
    if (cpu > 80 or mem_ratio > 0.9) and plan == "free":
        return "posible_abuso"
    if cpu > 70 or mem_ratio > 0.85:
        return "upgrade"
    return "ok"


@router.get("/resources/users")
def get_resources_users(admin: dict = Depends(require_role("admin"))):
    """Per-user (tenant) aggregation: total CPU, RAM, traffic, backup, cost/margin."""
    from app.infra.db import get_connection, release_connection

    _COST_PER_HOSTING = 2.0  # estimated USD/month per container

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT plan_name, monthly_price_usd FROM plan_economics")
        _plan_rows = cur.fetchall()
        _REVENUE = (
            {r["plan_name"]: float(r["monthly_price_usd"] or 0) for r in _plan_rows}
            if _plan_rows
            else {"free": 0, "personal": 9, "negocio": 19, "agencia": 39, "agencia_pro": 59}
        )
        cur.execute(
            """SELECT
                 u.user_id, u.email, u.plan,
                 COALESCE(u.billing_interval, 'yearly') AS billing_interval,
                 u.subscription_status,
                 COUNT(DISTINCT h.hosting_id)                                 AS hosting_count,
                 -- Latest resource snapshot aggregated per user
                 ROUND(AVG(latest.cpu_pct)::numeric, 1)                      AS avg_cpu_pct,
                 ROUND(SUM(latest.mem_mb)::numeric, 0)                       AS total_ram_mb,
                 ROUND(SUM(latest.disk_mb)::numeric, 0)                      AS total_disk_mb,
                 ROUND(SUM(latest.net_rx_mb)::numeric, 1)                    AS total_net_rx_mb,
                 ROUND(SUM(latest.net_tx_mb)::numeric, 1)                    AS total_net_tx_mb,
                 -- Traffic last 24 h (all hostings)
                 COALESCE(SUM(ts.requests_24h), 0)                           AS requests_24h,
                 COALESCE(SUM(ts.errors_4xx), 0) + COALESCE(SUM(ts.errors_5xx), 0) AS errors_24h,
                 -- Backup storage
                 COALESCE(SUM(bs.backup_mb), 0)                              AS total_backup_mb
               FROM users u
               JOIN hostings h ON h.user_id = u.user_id AND h.status NOT IN ('deleted','expired')
               -- Latest resource sample per hosting (adaptive window: latest-3min or 10min floor)
               LEFT JOIN LATERAL (
                   SELECT cpu_pct, mem_mb, disk_mb, net_rx_mb, net_tx_mb
                   FROM hosting_resource_samples
                   WHERE hosting_id = h.hosting_id
                     AND sampled_at >= (
                         SELECT COALESCE(
                           GREATEST(MAX(sampled_at) - INTERVAL '3 minutes', NOW() - INTERVAL '10 minutes'),
                           NOW() - INTERVAL '10 minutes'
                         ) FROM hosting_resource_samples
                     )
                   ORDER BY sampled_at DESC LIMIT 1
               ) latest ON TRUE
               LEFT JOIN LATERAL (
                   SELECT COALESCE(SUM(total_requests), 0) AS requests_24h,
                          COALESCE(SUM(errors_4xx), 0)     AS errors_4xx,
                          COALESCE(SUM(errors_5xx), 0)     AS errors_5xx
                   FROM traffic_stats
                   WHERE container_name = h.container_name
                     AND collected_at::TIMESTAMPTZ >= NOW() - INTERVAL '24 hours'
               ) ts ON TRUE
               LEFT JOIN LATERAL (
                   SELECT COALESCE(SUM(size_bytes), 0) / 1048576.0 AS backup_mb
                   FROM backups
                   WHERE hosting_id = h.hosting_id AND status = 'completed'
               ) bs ON TRUE
               GROUP BY u.user_id, u.email, u.plan, u.billing_interval, u.subscription_status
               ORDER BY total_ram_mb DESC NULLS LAST"""
        )
        rows = [dict(r) for r in cur.fetchall()]

        for r in rows:
            plan = r.get("plan") or "free"
            revenue = _REVENUE.get(plan, 0)
            cost    = float(r.get("hosting_count") or 0) * _COST_PER_HOSTING
            margin  = revenue - cost

            r["estimated_cost"] = round(cost, 2)
            r["revenue"]        = revenue
            r["margin"]         = round(margin, 2)

            cpu  = r.get("avg_cpu_pct") or 0
            ram  = r.get("total_ram_mb") or 0
            err  = r.get("errors_24h") or 0
            if margin < 0 and plan != "free":
                r["recommendation"] = "margen_negativo"
            elif (cpu > 70 or ram > 800) and plan == "free":
                r["recommendation"] = "posible_abuso"
            elif cpu > 70 or err > 50:
                r["recommendation"] = "revisar"
            else:
                r["recommendation"] = "ok"

        return {"items": rows, "count": len(rows)}
    finally:
        release_connection(conn)


@router.get("/users/{user_id}/backups")
def admin_list_user_backups(
    user_id: int,
    hosting_id: Optional[int] = None,
    limit: int = 50,
    admin: dict = Depends(require_role("admin")),
):
    """List all backups for a user (admin view — no ownership check)."""
    from app.services.backup_service import admin_list_backups
    return {"items": admin_list_backups(user_id=user_id, hosting_id=hosting_id, limit=limit)}


@router.get("/backups/{backup_id}/download")
async def admin_download_backup(
    request: Request,
    backup_id: int,
    background_tasks: BackgroundTasks,
    admin: dict = Depends(require_role("admin")),
):
    """Download any backup as admin. Logged to admin_audit_log."""
    from app.services.backup_service import admin_get_backup, build_download_package

    backup = await asyncio.get_running_loop().run_in_executor(
        None, lambda: admin_get_backup(backup_id)
    )
    if not backup:
        raise HTTPException(status_code=404, detail="Backup no encontrado")
    if backup["status"] != "completed":
        raise HTTPException(status_code=400, detail="Solo se pueden descargar backups completados")

    has_any = (
        (backup.get("db_path") and Path(backup["db_path"]).exists()) or
        (backup.get("files_path") and Path(backup["files_path"]).exists())
    )
    if not has_any:
        raise HTTPException(status_code=410, detail="Archivos no disponibles en disco")

    loop = asyncio.get_running_loop()
    tmp_path, filename = await loop.run_in_executor(
        None, lambda: build_download_package(backup)
    )
    background_tasks.add_task(lambda: tmp_path.unlink(missing_ok=True))

    _admin_audit.log(
        admin_id=admin["user_id"],
        admin_email=admin.get("email", ""),
        action="admin_download_backup",
        target_user_id=backup["user_id"],
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        details=(
            f"backup_id={backup_id} hosting_id={backup['hosting_id']} "
            f"site={backup.get('site_name')} file={filename}"
        ),
    )

    return FileResponse(
        path=str(tmp_path),
        filename=filename,
        media_type="application/gzip",
    )


@router.delete("/backups/{backup_id}")
def admin_delete_backup(
    request: Request,
    backup_id: int,
    admin: dict = Depends(require_role("admin")),
):
    """Delete any backup (admin). Removes DB record + physical files. Logged."""
    from app.services.backup_service import admin_get_backup, delete_backup

    backup = admin_get_backup(backup_id)
    if not backup:
        raise HTTPException(status_code=404, detail="Backup no encontrado")

    delete_backup(backup_id, admin=True)

    _admin_audit.log(
        admin_id=admin["user_id"],
        admin_email=admin.get("email", ""),
        action="admin_delete_backup",
        target_user_id=backup["user_id"],
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        details=(
            f"backup_id={backup_id} hosting_id={backup['hosting_id']} "
            f"site={backup.get('site_name')} status={backup['status']}"
        ),
    )
    return {"status": "deleted", "backup_id": backup_id}


@router.get("/pixel/site-by-domain")
def pixel_site_by_domain(domain: str, _: dict = Depends(require_role("admin"))):
    """Lookup the pixel_sites record for a given domain (e.g. 'hostingguard.lat')."""
    site = _pixel_repo.get_site_by_domain(domain)
    if not site:
        raise HTTPException(status_code=404, detail=f"No pixel site registered for domain '{domain}'")
    return site


@router.post("/pixel/setup-own-site")
def pixel_setup_own_site(admin: dict = Depends(require_role("admin"))):
    """Create (or return existing) pixel site for hostingguard.lat.
    Idempotent — safe to call multiple times."""
    domain = "hostingguard.lat"
    existing = _pixel_repo.get_site_by_domain(domain)
    if existing:
        site_id = existing["site_id"]
    else:
        site_id = _pixel_repo.create_site(
            user_id=admin["user_id"],
            name="HostingGuard",
            domain=domain,
        )
    snippet = f'<script src="https://api.hostingguard.lat/pixel.js?id={site_id}" defer></script>'
    return {"site_id": site_id, "domain": domain, "snippet": snippet, "created": not existing}


@router.get("/pixel/overview")
def pixel_overview(site_id: str = None, _: dict = Depends(require_role("admin"))):
    if site_id:
        return _pixel_repo.get_stats_for_site(site_id)
    return _pixel_repo.get_overview_admin()


@router.get("/pixel/events")
def pixel_events(limit: int = 100, offset: int = 0, site_id: str = None, _: dict = Depends(require_role("admin"))):
    if site_id:
        return _pixel_repo.get_events_for_site(site_id=site_id, limit=limit, offset=offset)
    return _pixel_repo.get_all_events_admin(limit=limit, offset=offset)


@router.get("/orchestrator/events")
def get_orchestrator_events(limit: int = 200, _: dict = Depends(require_role("admin"))):
    """Eventos globales del orquestador (throttle, autoscale, restart) de todos los usuarios."""
    return _hosting_repo.get_all_orchestrator_events(limit=limit)


# ---------------------------------------------------------------------------
# Admin hosting actions — sin filtro por user_id
# ---------------------------------------------------------------------------

def _get_ip(request: Request) -> str:
    for h in ("X-Real-IP", "X-Forwarded-For"):
        v = request.headers.get(h)
        if v:
            return v.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/hostings/{hosting_id}/restart")
@limiter.limit("30/minute")
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
@limiter.limit("30/minute")
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
@limiter.limit("30/minute")
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


@router.post("/hostings/purge-deleted")
@limiter.limit("5/minute")
async def admin_purge_deleted_hostings(
    request: Request,
    admin: dict = Depends(require_role("admin")),
):
    """
    Hard-delete all hostings with status 'deleted' or 'zombie' that were soft-deleted
    previously. Purges all their child records and removes the hosting row completely.
    Safe to run multiple times (idempotent).
    """
    from app.infra.db import get_connection, release_connection
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT hosting_id, container_name FROM hostings WHERE status IN ('deleted', 'zombie')"
        )
        rows = cursor.fetchall()
    finally:
        release_connection(conn)

    purged = []
    errors = []
    for row in rows:
        hosting_id     = row["hosting_id"]
        container_name = row["container_name"]
        db_container   = container_name.replace("_wp_", "_db_", 1) if "_wp_" in container_name else None
        try:
            _hosting_repo.admin_delete_hosting(hosting_id, db_container=db_container)
            purged.append({"hosting_id": hosting_id, "container": container_name})
        except Exception as exc:
            errors.append({"hosting_id": hosting_id, "error": str(exc)})

    _hosting_repo.log_orchestrator_event(
        container_name="—",
        user_id=admin["user_id"],
        event_type="admin_purge_deleted",
        message=f"Admin {admin['email']} purgó {len(purged)} hosting(s) soft-deleted. Errors: {len(errors)}",
    )
    return {"ok": True, "purged": len(purged), "errors": errors, "detail": purged}


@router.api_route("/hostings/{hosting_id}/terminate", methods=["DELETE", "POST"])
@limiter.limit("10/minute")
async def admin_terminate_hosting(
    hosting_id: int,
    request: Request,
    admin: dict = Depends(require_role("admin")),
):
    """
    Terminación forzada por el admin. Idempotente: funciona aunque el contenedor
    Docker ya no exista (hosting huérfano). Nunca devuelve 500 por contenedor faltante.
    Responde 200 con warnings[] si hubo problemas no fatales.
    """
    # Parse body manually so DELETE + JSON body always works regardless of
    # Pydantic/FastAPI body-parsing quirks for non-POST methods.
    try:
        body_data = await request.json()
    except Exception:
        body_data = {}

    reason = (body_data.get("reason") or request.query_params.get("reason") or "").strip()
    description = (body_data.get("description") or request.query_params.get("description") or "").strip()

    if not reason:
        raise HTTPException(status_code=400, detail="Se requiere una razón para la terminación.")

    hosting = _hosting_repo.get_hosting_any(hosting_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting no encontrado")

    warnings: list[str] = []
    container    = hosting.get("container_name") or ""
    db_container = container.replace("_wp_", "_db_", 1) if "_wp_" in container else None
    targets      = [c for c in [container, db_container] if c]

    # 1. Remove containers — tolerate "No such container" as a warning, not an error
    for cname in targets:
        try:
            r = await _run_docker("docker", "rm", "-f", cname, timeout=15)
            if r.returncode != 0:
                stderr = (r.stderr or "").strip()
                if "No such container" in stderr or "no such container" in stderr.lower():
                    warnings.append(f"Docker container not found: {cname}")
                    logger.warning("admin_terminate: container %s not found in Docker (orphaned hosting)", cname)
                else:
                    warnings.append(f"docker rm warning for {cname}: {stderr[:120]}")
                    logger.warning("admin_terminate: docker rm %s: %s", cname, stderr[:200])
        except Exception as exc:
            warnings.append(f"docker rm error for {cname}: {exc}")
            logger.warning("admin_terminate: docker rm exception for %s: %s", cname, exc)

    # 2. Clean up custom domains: remove Traefik configs + delete DB records
    try:
        from app.infra.audit.domain_repository import DomainRepository
        from app.services.domain_checker import remove_traefik_config
        _domain_repo = DomainRepository()
        hosting_user_id = hosting["user_id"]
        domains = _domain_repo.get_domains(hosting_id, hosting_user_id)
        for d in domains:
            try:
                remove_traefik_config(d["domain_id"])
            except Exception as exc:
                warnings.append(f"traefik cleanup warning for domain {d.get('domain_id')}: {exc}")
            try:
                _domain_repo.delete_domain(d["domain_id"], hosting_user_id)
            except Exception:
                pass
    except Exception as exc:
        warnings.append(f"domain cleanup error: {exc}")
        logger.warning("admin_terminate: domain cleanup error for hosting %s: %s", hosting_id, exc)

    # 3. Audit log BEFORE modifying DB (non-fatal)
    try:
        _hosting_repo.log_orchestrator_event(
            container or "—", hosting["user_id"],
            "admin_terminate",
            f"TERMINADO por admin {admin['email']} | Razón: {reason} | IP: {_get_ip(request)}"
            + (f" | warnings: {warnings}" if warnings else ""),
        )
    except Exception as exc:
        warnings.append(f"audit log error: {exc}")
        logger.warning("admin_terminate: orchestrator log failed for hosting %s: %s", hosting_id, exc)

    # 4. Activity event log (non-fatal)
    try:
        from app.services.activity_service import log_event as _log_activity
        _log_activity(
            user_id=hosting["user_id"], hosting_id=hosting_id,
            event_type="hosting_terminated_by_admin",
            category="hosting", severity="critical",
            title=f"Hosting terminado por admin: {hosting.get('name', str(hosting_id))}",
            message=f"Admin: {admin['email']} | Razón: {reason}"
            + (f" | {description}" if description else ""),
            source="admin",
        )
    except Exception as exc:
        warnings.append(f"activity log error: {exc}")
        logger.warning("admin_terminate: activity log failed for hosting %s: %s", hosting_id, exc)

    # 5. Hard-delete DB — this is the only fatal step
    try:
        _hosting_repo.admin_delete_hosting(hosting_id, db_container=db_container)
    except Exception as exc:
        logger.error("admin_terminate: DB delete failed for hosting %s: %s", hosting_id, exc)
        raise HTTPException(
            status_code=500,
            detail=f"DB cleanup failed: {exc}",
        )

    # 6. Remove residual client directory from host filesystem (non-fatal)
    if container:
        import shutil as _shutil
        _OPT_CLIENTS = "/opt/clients"
        _safe_base = os.path.realpath(_OPT_CLIENTS)
        _candidate = os.path.realpath(os.path.join(_OPT_CLIENTS, container))
        if not _candidate.startswith(_safe_base + os.sep):
            warnings.append("client dir cleanup skipped: path traversal detected")
            logger.warning("admin_terminate: path traversal blocked for container %r", container)
        elif os.path.isdir(_candidate):
            try:
                _shutil.rmtree(_candidate)
                logger.info("admin_terminate: removed client dir %s", _candidate)
            except Exception as exc:
                warnings.append(f"client dir cleanup warning: {exc}")
                logger.warning("admin_terminate: could not remove %s: %s", _candidate, exc)

    return {
        "status": "terminated",
        "hosting_id": hosting_id,
        "container": container or None,
        "reason": reason,
        "admin": admin["email"],
        "warnings": warnings,
        "at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/resources/container-status")
def get_container_status(admin: dict = Depends(require_role("admin"))):
    """Accurate breakdown: DB hostings vs actually-running Docker containers.
    Exposes orphaned hostings (active in DB but container missing from Docker).
    """
    import subprocess as _sp
    from app.infra.db import get_connection, release_connection

    # 1. DB counts
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT
                 COUNT(*) FILTER (WHERE status = 'active')         AS active_db,
                 COUNT(*) FILTER (WHERE status NOT IN ('deleted','expired')) AS total_alive_db
               FROM hostings WHERE container_name IS NOT NULL"""
        )
        db_row = dict(cur.fetchone() or {})
        cur.execute(
            "SELECT hosting_id, container_name FROM hostings "
            "WHERE status = 'active' AND container_name IS NOT NULL"
        )
        active_rows = [dict(r) for r in cur.fetchall()]
    finally:
        release_connection(conn)

    # 2. Docker ps — get all running container names
    try:
        ps = _sp.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=10,
        )
        running_names = {n.strip().lstrip("/") for n in ps.stdout.splitlines() if n.strip()}
    except Exception:
        running_names = set()

    # 3. Classify containers
    client_running   = {n for n in running_names if n.startswith("user_")}
    platform_running = {n for n in running_names if not n.startswith("user_")}

    # 4. Orphaned: active in DB but not running in Docker
    orphaned = [
        {"hosting_id": r["hosting_id"], "container_name": r["container_name"]}
        for r in active_rows
        if r["container_name"] not in running_names
    ]

    return {
        "hostings_active_db":       db_row.get("active_db", 0),
        "hostings_alive_db":        db_row.get("total_alive_db", 0),
        "containers_client_running": len(client_running),
        "containers_platform_running": len(platform_running),
        "containers_total_running":  len(running_names),
        "hostings_orphaned_count":  len(orphaned),
        "hostings_orphaned":        orphaned,
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

        # Plan revenue from plan_economics (source of truth)
        cursor.execute("SELECT plan_name, monthly_price_usd FROM plan_economics")
        _pe_rows = cursor.fetchall()
        PLAN_REVENUE = (
            {r["plan_name"]: float(r["monthly_price_usd"] or 0) for r in _pe_rows}
            if _pe_rows
            else {"free": 0.0, "personal": 9.0, "negocio": 19.0, "agencia": 39.0,
                  "agencia_pro": 59.0, "enterprise_annual": 99.0, "enterprise_monthly": 129.0}
        )

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
    try:
        from app.services.activity_service import log_event as _log
        _log(user_id=admin["user_id"], actor_type="admin", actor_email=admin.get("email"),
             event_type="admin_changed_plan", category="admin", severity="warning",
             title=f"Admin cambió plan de {user.get('email', user_id)} → {body.plan}",
             ip=_get_ip(request), source="admin",
             metadata={"target_user_id": user_id, "target_email": user.get("email"),
                       "new_plan": body.plan, "hostings_updated": len(hostings)})
    except Exception:
        pass
    return {
        "ok": True,
        "plan": body.plan,
        "hostings_updated": len(hostings),
        "docker_errors": docker_errors,
    }


@router.delete("/users/{user_id}")
async def admin_delete_user(user_id: int, admin: dict = Depends(require_role("admin"))):
    """
    Hard-delete a user account and ALL their data (hostings, containers, events, sessions).

    Cascade order:
      1. docker rm -f each hosting container + DB container (silent on 'no such container')
      2. admin_delete_hosting: removes all child DB records + hosting row
      3. delete_user: removes orchestrator_events, support_sessions, user row
    """
    target = _user_repo.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if target.get("role") == "admin":
        raise HTTPException(status_code=403, detail="No se puede eliminar una cuenta admin")

    hostings = _hosting_repo.get_user_hostings(user_id)
    docker_errors = []

    for h in hostings:
        container    = h["container_name"]
        db_container = container.replace("_wp_", "_db_", 1) if "_wp_" in container else None
        targets      = [container] + ([db_container] if db_container else [])

        # 1. Remove Docker containers (ignore 'no such container')
        for cname in targets:
            r = await _run_docker("docker", "rm", "-f", cname, timeout=15)
            if r.returncode != 0 and "No such container" not in (r.stderr or ""):
                docker_errors.append(f"{cname}: {(r.stderr or '').strip()[:80]}")

        # 2. Hard-delete hosting + all child records
        _hosting_repo.admin_delete_hosting(h["hosting_id"], db_container=db_container)

    # 3. Delete user (clears orchestrator_events, support_sessions, user row)
    deleted = _user_repo.delete_user(user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    try:
        from app.services.activity_service import log_event as _log
        _log(user_id=admin["user_id"], actor_type="admin", actor_email=admin.get("email"),
             event_type="admin_deleted_user", category="admin", severity="critical",
             title=f"Admin eliminó cuenta: {target['email']}",
             source="admin",
             metadata={"deleted_user_id": user_id, "deleted_email": target["email"],
                       "hostings_removed": len(hostings)})
    except Exception:
        pass

    return {
        "ok": True,
        "deleted_user_id": user_id,
        "email": target["email"],
        "hostings_removed": len(hostings),
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

    # Always hard-delete — force cleanup overrides the normal safety gate
    _hosting_repo.admin_delete_hosting(hosting_id, db_container=db_container)

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


# ── Admin notification broadcast ────────────────────────────────────────────

class BroadcastRequest(BaseModel):
    title:        str           = Field(..., min_length=1, max_length=200)
    message:      str           = Field(..., min_length=1, max_length=1000)
    category:     str           = Field(default="system")
    severity:     str           = Field(default="info")
    channel:      str           = Field(default="dashboard")
    action_url:   Optional[str] = None
    target_type:  str           = Field(default="all")
    target_value: Optional[str] = None


@router.post("/notifications/broadcast")
def admin_broadcast_notification(
    body: BroadcastRequest,
    request: Request,
    admin: dict = Depends(require_role("admin")),
):
    from app.services.notification_service import get_target_user_ids, notify_bulk

    valid_targets = {"all", "user", "plan", "site_down", "pending_payment", "high_usage"}
    if body.target_type not in valid_targets:
        raise HTTPException(status_code=422, detail=f"target_type must be one of {valid_targets}")

    user_ids = get_target_user_ids(body.target_type, body.target_value)
    if not user_ids:
        return {"ok": True, "sent": 0, "message": "No users matched the target"}

    count = notify_bulk(
        user_ids=user_ids,
        title=body.title,
        message=body.message,
        category=body.category,
        severity=body.severity,
        channel=body.channel,
        action_url=body.action_url,
        admin_id=admin["user_id"],
    )

    _admin_audit.log(
        admin_id=admin["user_id"],
        admin_email=admin["email"],
        action="notification_broadcast",
        ip=_get_ip(request),
        details=f"target={body.target_type} sent={count} title={body.title[:60]!r}",
    )
    try:
        from app.services.activity_service import log_event as _log
        _log(user_id=admin["user_id"], actor_type="admin", actor_email=admin.get("email"),
             event_type="admin_sent_notification", category="admin", severity="info",
             title=f"Admin envió notificación: {body.title[:80]}",
             ip=_get_ip(request), source="admin",
             metadata={"target_type": body.target_type, "sent": count, "category": body.category})
    except Exception:
        pass

    return {"ok": True, "sent": count, "target_type": body.target_type}


@router.get("/notifications/history")
def admin_notification_history(admin: dict = Depends(require_role("admin"))):
    return {"items": _notif_repo.get_admin_history(limit=100)}


@router.get("/notifications/log")
def admin_notification_log(
    limit:    int = 200,
    category: Optional[str] = None,
    severity: Optional[str] = None,
    source:   Optional[str] = None,
    admin: dict = Depends(require_role("admin")),
):
    """Full notification audit log — all automatic + manual, with recipient email."""
    items = _notif_repo.get_full_log(
        limit=min(limit, 500),
        category=category or None,
        severity=severity or None,
        source=source or None,
    )
    return {"items": items, "total": len(items)}


@router.get("/audit-log")
def admin_audit_log(
    limit: int = 100,
    admin: dict = Depends(require_role("admin")),
):
    return {"items": _admin_audit.get_recent(limit=min(limit, 500))}


# ═══════════════════════════════════════════════════════════════════════════════
# Security Center
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/security/status")
def get_security_status(admin: dict = Depends(require_role("admin"))):
    """Traffic-light aggregate for open security_events.

    Returns status (green/yellow/red), label, counts per severity, and
    the top 5 open events — used by SecurityStatusBeacon in the admin header.
    """
    from app.infra.db import get_connection, release_connection
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT event_type, severity, hosting_id, title, count, last_seen
            FROM   security_events
            WHERE  status = 'open'
            ORDER BY
                CASE severity
                    WHEN 'critical' THEN 1
                    WHEN 'high'     THEN 2
                    WHEN 'medium'   THEN 3
                    WHEN 'warning'  THEN 4
                    ELSE 5
                END,
                last_seen DESC
            LIMIT 20
            """
        )
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        release_connection(conn)

    counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "warning": 0}
    for r in rows:
        sev = r.get("severity", "")
        if sev in counts:
            counts[sev] += 1

    if counts["critical"] > 0 or counts["high"] > 0:
        status = "red"
        label  = "Alerta de seguridad activa"
    elif counts["medium"] > 0 or counts["warning"] > 0:
        status = "yellow"
        label  = "Actividad sospechosa detectada"
    else:
        status = "green"
        label  = "Sin alertas activas"

    top_events = [
        {
            "event_type": r["event_type"],
            "severity":   r["severity"],
            "hosting_id": r["hosting_id"],
            "title":      r["title"],
            "count":      r.get("count"),
            "last_seen":  (
                r["last_seen"].isoformat()
                if hasattr(r.get("last_seen"), "isoformat")
                else str(r.get("last_seen") or "")
            ),
        }
        for r in rows[:5]
    ]

    return {
        "status":            status,
        "label":             label,
        "open_events_total": len(rows),
        "critical_count":    counts["critical"],
        "high_count":        counts["high"],
        "medium_count":      counts["medium"],
        "warning_count":     counts["warning"],
        "top_events":        top_events,
    }


@router.get("/security/summary")
def get_security_summary(admin: dict = Depends(require_role("admin"))):
    """Dashboard cards data for the Security Center."""
    from app.services.security_event_service import get_security_summary
    from app.services.activity_service import mask_ip
    summary = get_security_summary()
    # Mask IPs in top_suspect_ips
    for entry in summary.get("top_suspect_ips", []):
        entry["ip"] = mask_ip(entry.get("ip"))
    return summary


@router.get("/security/events")
def list_security_events(
    severity:   Optional[str] = None,
    category:   Optional[str] = None,
    status:     Optional[str] = None,
    user_id:    Optional[int] = None,
    hosting_id: Optional[int] = None,
    date_from:  Optional[str] = None,
    date_to:    Optional[str] = None,
    search:     Optional[str] = None,
    limit:  int = 100,
    offset: int = 0,
    admin: dict = Depends(require_role("admin")),
):
    """Filterable security event log."""
    from app.services.security_event_service import query_security_events
    from app.services.activity_service import mask_ip
    events = query_security_events(
        severity=severity, category=category, status=status,
        user_id=user_id, hosting_id=hosting_id,
        date_from=date_from, date_to=date_to, search=search,
        limit=min(limit, 500), offset=offset,
    )
    for e in events:
        e["ip"] = mask_ip(e.get("ip"))
    return {"items": events, "limit": limit, "offset": offset}


@router.post("/security/events/{event_id}/resolve")
def resolve_security_event(
    event_id: int,
    request: Request,
    admin: dict = Depends(require_role("admin")),
):
    """Mark a security event as resolved."""
    from app.services.security_event_service import resolve_security_event as _resolve
    ok = _resolve(event_id, resolved_by=admin["user_id"])
    if not ok:
        raise HTTPException(status_code=404, detail="Evento no encontrado o ya resuelto")
    _admin_audit.log(
        admin_id=admin["user_id"],
        admin_email=admin.get("email", ""),
        action="security_event_resolved",
        ip=_get_ip(request),
        details=f"event_id={event_id}",
    )
    try:
        from app.services.activity_service import log_event as _log
        _log(user_id=admin["user_id"], actor_type="admin", actor_email=admin.get("email"),
             event_type="admin_resolved_security_event", category="admin", severity="info",
             title=f"Admin resolvió evento de seguridad #{event_id}",
             ip=_get_ip(request), source="admin",
             metadata={"security_event_id": event_id})
    except Exception:
        pass
    return {"ok": True, "event_id": event_id}


@router.get("/security/events/{event_id}/ai-summary")
@limiter.limit("20/hour")
async def security_event_ai_summary(
    request: Request,
    event_id: int,
    admin: dict = Depends(require_role("admin")),
):
    """Optional AI incident summary for a security event."""
    from app.api.config import ENABLE_AI_ADVISORY
    from app.infra.db import get_connection, release_connection
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM security_events WHERE event_id = %s", (event_id,))
        row = cur.fetchone()
    finally:
        release_connection(conn)

    if not row:
        raise HTTPException(status_code=404, detail="Evento no encontrado")

    event = dict(row)

    if not ENABLE_AI_ADVISORY:
        return {
            "ok": False,
            "reason": "AI advisory is disabled (ENABLE_AI_ADVISORY=false)",
            "event": event,
        }

    try:
        from app.services.ai_advisor import get_client
        import json as _json

        client = get_client()
        prompt = f"""Analiza este evento de seguridad de una plataforma SaaS de hosting:

Tipo: {event['event_type']}
Categoría: {event['category']}
Severidad: {event['severity']}
Título: {event['title']}
Mensaje: {event.get('message', 'N/A')}
IP: {event.get('ip', 'desconocida')}
Metadata: {_json.dumps(event.get('metadata') or {}, ensure_ascii=False)}

Responde en JSON con:
- causa_probable: string
- evidencia: string
- impacto: string
- acciones_recomendadas: string[]
- notificar_cliente: bool
- aplicar_proteccion: bool

IMPORTANTE: La IA NO debe bloquear IPs ni suspender usuarios. Solo recomendar."""

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        # Extract JSON block
        import re as _re
        m = _re.search(r'\{.*\}', raw, _re.DOTALL)
        summary = _json.loads(m.group()) if m else {"raw": raw}
        return {"ok": True, "event_id": event_id, "summary": summary}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI summary failed: {exc}")


class ProtectionModeBody(BaseModel):
    enabled:              bool = True
    block_xmlrpc:         bool = False
    rate_limit_wp_login:  bool = False
    block_scanner_paths:  bool = False
    elevated_sensitivity: bool = False


@router.post("/hostings/{hosting_id}/protection-mode")
def set_protection_mode(
    hosting_id: int,
    body: ProtectionModeBody,
    request: Request,
    admin: dict = Depends(require_role("admin")),
):
    """Enable/disable protection mode settings for a hosting."""
    from app.infra.db import get_connection, release_connection
    import json as _json
    from datetime import datetime, timezone

    settings = {
        "enabled":              body.enabled,
        "block_xmlrpc":         body.block_xmlrpc,
        "rate_limit_wp_login":  body.rate_limit_wp_login,
        "block_scanner_paths":  body.block_scanner_paths,
        "elevated_sensitivity": body.elevated_sensitivity,
        "set_at":               datetime.now(timezone.utc).isoformat(),
        "set_by":               admin["user_id"],
    }

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE hostings SET protection_mode = %s WHERE hosting_id = %s RETURNING hosting_id",
            (_json.dumps(settings), hosting_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Hosting no encontrado")
        conn.commit()
    except HTTPException:
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        release_connection(conn)

    _admin_audit.log(
        admin_id=admin["user_id"],
        admin_email=admin.get("email", ""),
        action="protection_mode_set",
        ip=_get_ip(request),
        details=f"hosting_id={hosting_id} enabled={body.enabled} settings={_json.dumps(settings)[:200]}",
    )

    from app.services.activity_service import log_event
    log_event(
        hosting_id=hosting_id,
        actor_type="admin",
        actor_user_id=admin["user_id"],
        actor_email=admin.get("email"),
        event_type="protection_mode_changed",
        category="security",
        severity="warning" if body.enabled else "info",
        title=f"Modo protección {'activado' if body.enabled else 'desactivado'}",
        source="admin",
        metadata=settings,
    )

    return {"ok": True, "hosting_id": hosting_id, "protection_mode": settings}


@router.get("/hostings/{hosting_id}/protection-mode")
def get_protection_mode(
    hosting_id: int,
    admin: dict = Depends(require_role("admin")),
):
    """Get current protection mode settings for a hosting."""
    from app.infra.db import get_connection, release_connection
    import json as _json

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT hosting_id, name, protection_mode FROM hostings WHERE hosting_id = %s",
            (hosting_id,),
        )
        row = cur.fetchone()
    finally:
        release_connection(conn)

    if not row:
        raise HTTPException(status_code=404, detail="Hosting no encontrado")

    row = dict(row)
    pm = row.get("protection_mode") or {}
    if isinstance(pm, str):
        try:
            pm = _json.loads(pm)
        except Exception:
            pm = {}

    return {"hosting_id": hosting_id, "name": row.get("name"), "protection_mode": pm}


# ── AI Sentinel — system_incidents ───────────────────────────────────────────

@router.get("/sentinel/incidents")
def list_sentinel_incidents(
    source_type: Optional[str] = None,
    status:      Optional[str] = None,
    user_id:     Optional[int] = None,
    severity:    Optional[str] = None,
    limit:       int = 100,
    offset:      int = 0,
    _: dict = Depends(require_role("admin")),
):
    """List system_incidents with latest ai_diagnosis per incident via LATERAL JOIN."""
    from app.infra.db import get_connection, release_connection
    conn = get_connection()
    try:
        where: list = []
        params: list = []
        if source_type:
            where.append("si.source_type = %s"); params.append(source_type)
        if status:
            where.append("si.status = %s"); params.append(status)
        if user_id:
            where.append("si.user_id = %s"); params.append(user_id)
        if severity:
            where.append("si.severity = %s"); params.append(severity)
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        params += [min(limit, 500), offset]
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT si.*,
                   diag.id            AS diagnosis_id,
                   diag.summary       AS diagnosis_summary,
                   diag.root_cause    AS diagnosis_root_cause,
                   diag.recommended_next_steps AS diagnosis_steps,
                   diag.customer_message       AS diagnosis_customer_message,
                   diag.confidence    AS diagnosis_confidence,
                   diag.model         AS diagnosis_model,
                   diag.updated_at    AS diagnosis_updated_at,
                   diag.fingerprint   AS diagnosis_source
              FROM system_incidents si
              LEFT JOIN LATERAL (
                SELECT id, summary, root_cause, recommended_next_steps,
                       customer_message, confidence, model, updated_at, fingerprint
                  FROM ai_diagnosis
                 WHERE incident_id = si.incident_id
                 ORDER BY created_at DESC
                 LIMIT 1
              ) diag ON TRUE
            {clause}
             ORDER BY si.last_seen DESC LIMIT %s OFFSET %s
            """,
            params,
        )
        rows = [dict(r) for r in cur.fetchall()]
        return {"items": rows, "limit": limit, "offset": offset, "count": len(rows)}
    finally:
        release_connection(conn)


@router.get("/incidents/{incident_id}/diagnosis")
def get_incident_diagnosis(
    incident_id: int,
    _: dict = Depends(require_role("admin")),
):
    """Return the latest ai_diagnosis for a given incident."""
    from app.infra.db import get_connection, release_connection
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, incident_id, source_type, incident_type, severity,
                   summary, root_cause, recommended_next_steps,
                   customer_message, admin_notes, confidence,
                   model, prompt_version, fingerprint AS diagnosis_source,
                   status, error_message, context_hash,
                   created_at, updated_at
              FROM ai_diagnosis
             WHERE incident_id = %s
             ORDER BY created_at DESC
             LIMIT 1
            """,
            (incident_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No hay diagnóstico disponible para este incidente")
        return dict(row)
    finally:
        release_connection(conn)


@router.post("/incidents/{incident_id}/diagnose")
def trigger_incident_diagnosis(
    incident_id: int,
    background_tasks: BackgroundTasks,
    admin: dict = Depends(require_role("admin")),
):
    """Trigger an on-demand AI diagnosis for a specific incident."""
    from app.infra.db import get_connection, release_connection

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT incident_id, source_type, incident_type, severity, title, "
            "summary, evidence, count, hosting_id, user_id, first_seen, last_seen, updated_at "
            "FROM system_incidents WHERE incident_id = %s",
            (incident_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Incidente no encontrado")
    finally:
        release_connection(conn)

    def _run_diagnosis():
        from app.infra.db import get_connection, release_connection
        from app.services.ai.run_ai_diagnostics import _get_existing_diagnosis, _save_diagnosis, _save_error
        from app.services.ai.diagnostic_context import build_incident_context, compute_context_hash
        from app.services.ai.llm_client import generate_diagnosis, AI_DIAGNOSTIC_PROMPT_VERSION
        dconn = get_connection()
        try:
            incident = dict(row)
            context = build_incident_context(dconn, incident)
            new_hash = compute_context_hash(incident)
            existing = _get_existing_diagnosis(dconn, incident_id)
            diagnosis, model = generate_diagnosis(context)
            existing_id = existing["id"] if existing else None
            _save_diagnosis(
                dconn,
                incident=incident,
                diagnosis=diagnosis,
                model=model,
                context_hash=new_hash,
                existing_id=existing_id,
                prompt_version=AI_DIAGNOSTIC_PROMPT_VERSION,
            )
            dconn.commit()
        except Exception as exc:
            logger.warning("on_demand_diagnosis(%s) failed: %s", incident_id, exc)
            try:
                dconn.rollback()
            except Exception:
                pass
        finally:
            release_connection(dconn)

    background_tasks.add_task(_run_diagnosis)
    return {"ok": True, "incident_id": incident_id, "status": "queued"}


@router.post("/incidents/{incident_id}/resolve")
def resolve_sentinel_incident(
    incident_id: int,
    request: Request,
    admin: dict = Depends(require_role("admin")),
):
    """Manually mark a system_incident as resolved."""
    import json as _json_mod
    from app.infra.db import get_connection, release_connection
    from datetime import datetime, timezone
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT incident_id, status FROM system_incidents WHERE incident_id = %s",
            (incident_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Incidente no encontrado")
        if dict(row)["status"] != "open":
            raise HTTPException(status_code=409, detail="El incidente ya está resuelto")

        now = datetime.now(timezone.utc)
        cur.execute(
            """
            UPDATE system_incidents
               SET status = 'resolved', resolved_at = %s, updated_at = %s,
                   evidence = evidence || %s::jsonb
             WHERE incident_id = %s AND status = 'open'
            """,
            (
                now, now,
                _json_mod.dumps({
                    "resolved_by":     f"admin:{admin['user_id']}",
                    "resolved_reason": "manual_resolve",
                }),
                incident_id,
            ),
        )
        conn.commit()
        _admin_audit.log(
            admin_id=admin["user_id"],
            admin_email=admin.get("email", ""),
            action="sentinel_incident_resolved",
            ip=_get_ip(request),
            details=f"incident_id={incident_id}",
        )
        return {"ok": True, "incident_id": incident_id}
    except HTTPException:
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        release_connection(conn)


@router.get("/deploy-events")
def list_admin_deploy_events(
    user_id:  Optional[int] = None,
    status:   Optional[str] = None,
    code:     Optional[str] = None,
    limit:    int = 100,
    offset:   int = 0,
    _: dict = Depends(require_role("admin")),
):
    """List all deploy_events with optional filters."""
    from app.infra.db import get_connection, release_connection
    conn = get_connection()
    try:
        where: list = []
        params: list = []
        if user_id:
            where.append("user_id = %s"); params.append(user_id)
        if status:
            where.append("status = %s"); params.append(status)
        if code:
            where.append("code = %s"); params.append(code)
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        params += [min(limit, 500), offset]
        cur = conn.cursor()
        cur.execute(
            f"SELECT deploy_event_id, user_id, hosting_id, repo_url, branch,"
            f"       project_name, stage, status, code, message, suggested_fix,"
            f"       evidence, cleanup_status, created_at"
            f"  FROM deploy_events {clause}"
            f" ORDER BY created_at DESC LIMIT %s OFFSET %s",
            params,
        )
        return {"items": [dict(r) for r in cur.fetchall()], "limit": limit, "offset": offset}
    finally:
        release_connection(conn)
