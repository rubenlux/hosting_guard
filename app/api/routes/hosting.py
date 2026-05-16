import subprocess
import uuid
import os
import re
import asyncio
import secrets
import shutil
import stat
import zipfile
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from app.api.security import verify_token, require_support_write
from app.api.rate_limit import limiter, DEPLOY_RATE_LIMIT
from app.services.deploy_diagnostics import DeployError
from app.services.deploy.project_detector import (
    _read_pkg, _is_web_buildable, _detect_out_dir, _find_buildable_roots,
)
from app.services.deploy.build_runner import (
    _docker_env_flags, _traefik_labels, _check_required_tool,
)
from app.services.deploy.github_deploy_service import run_github_deploy
from app.api.saturation_guard import docker_capacity, docker_op
from app.infra.audit.hosting_repository import HostingRepository
from app.infra.audit.user_repository import UserRepository
from app.infra.audit.health_repository import HealthRepository
from app.core.ai_orchestrator import AIOrchestrator
# Se importará de forma dinámica para evitar circulares si es necesario, 
# pero idealmente inyectamos la instancia.
from app.core.debug_context_builder import build_debug_context
from app.core.health_engine import calculate_health_score
from app.core.alert_engine import check_alerts
from app.infra.docker_client import run_docker_command_async
from app.infra.container_locks import container_lock
from app.api.wp_optimize import optimize_wordpress
from app.services.notification_service import notify

logger = logging.getLogger(__name__)

_user_repo = UserRepository()
hosting_repo = HostingRepository()
_health_repo = HealthRepository()

# --- Constantes de seguridad ---
MAX_ZIP_SIZE        = 500 * 1024 * 1024   # 500 MB en memoria
MAX_EXTRACTED_SIZE  = 2   * 1024 * 1024 * 1024   # 2 GB descomprimido (anti ZIP-bomb)
ALLOWED_REPO_HOSTS  = {"github.com", "gitlab.com", "bitbucket.org"}
BRANCH_REGEX        = re.compile(r'^[a-zA-Z0-9._/\-]+$')
PROJECT_NAME_REGEX  = re.compile(r'^[a-z0-9][a-z0-9\-]{1,48}[a-z0-9]$')
# Formatos válidos para --since de docker logs: "5m", "2h", "3d", "2024-01-15T10:00:00"
_SINCE_REGEX        = re.compile(r'^\d+[smhd]$|^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$')


# ── upload-zip security helpers ───────────────────────────────────────────────

class _ZipValidationError(Exception):
    def __init__(self, detail: str, reason: str):
        self.detail = detail
        self.reason = reason
        super().__init__(detail)


_BLOCKED_EXTENSIONS = frozenset({
    ".php", ".php3", ".php4", ".php5", ".phtml",
    ".py", ".pyc", ".pyo", ".pyw",
    ".rb", ".pl", ".cgi",
    ".sh", ".bash", ".zsh", ".fish", ".cmd", ".bat", ".ps1",
    ".exe", ".com", ".bin", ".dll", ".so", ".dylib",
    ".asp", ".aspx", ".jsp", ".jspx",
})

_SWAP_SKIP = frozenset({"_upload.zip", "_extracted", "_new", "_backup", ".git"})


def _log_static_upload_rejection(
    request, user_id: Optional[int], hosting_id: int,
    filename: str, size_bytes: int, reason: str,
) -> None:
    from app.services.security_event_service import log_security_event
    log_security_event(
        severity="warning",
        category="upload",
        event_type="static_upload_rejected_magic_bytes",
        title="Upload de sitio bloqueado por validación de archivo",
        message="El archivo subido no es un ZIP válido o contiene rutas inseguras.",
        user_id=user_id,
        hosting_id=hosting_id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        path=str(request.url.path),
        source="static_site_upload",
        metadata={
            "filename": filename,
            "suffix": ".zip",
            "size_bytes": size_bytes,
            "reason": reason,
            "action": "blocked",
        },
    )


def _safe_extract_zip(zf: zipfile.ZipFile, extracted_dir: Path) -> None:
    """Validate and extract each ZIP member individually. Raises _ZipValidationError on violation."""
    base = extracted_dir.resolve()
    for member in zf.infolist():
        name = member.filename
        if os.path.isabs(name):
            raise _ZipValidationError("ZIP contiene rutas absolutas", "absolute_path")
        if ".git" in Path(name).parts:
            raise _ZipValidationError("ZIP contiene entradas .git", "git_entry_blocked")
        if stat.S_ISLNK(member.external_attr >> 16):
            raise _ZipValidationError("ZIP contiene enlaces simbólicos", "symlink_detected")
        if not name.endswith("/"):
            ext = Path(name).suffix.lower()
            if ext in _BLOCKED_EXTENSIONS:
                raise _ZipValidationError(
                    f"Tipo de archivo no permitido: {ext}", "disallowed_file_type"
                )
        target = (base / name).resolve()
        if not str(target).startswith(str(base) + os.sep) and str(target) != str(base):
            raise _ZipValidationError(
                "ZIP contiene rutas que escapan del directorio destino (Zip Slip)",
                "zip_slip_path_traversal",
            )
        if name.endswith("/"):
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)


def _find_serve_dir(site_dir: str) -> str:
    # "public" is intentionally excluded — it's a CRA source template, not a build output
    for subdir in ["dist", "build", "www", "_site", "frontend/dist", "out"]:
        candidate = os.path.join(site_dir, subdir)
        if os.path.exists(os.path.join(candidate, "index.html")):
            return candidate
    return site_dir




def _validate_project_name(name: str) -> None:
    """Valida que el nombre sea un slug seguro para subdominios y labels de Traefik."""
    clean = name.lower().replace(" ", "-")
    if not PROJECT_NAME_REGEX.match(clean):
        raise HTTPException(
            status_code=400,
            detail="Nombre de proyecto inválido. Solo letras minúsculas, números y guiones (3-50 chars)."
        )


def _validate_repo_url(url: str) -> None:
    """Validates HTTPS URL from a trusted host with at least user/repo path."""
    url = url.strip()
    try:
        parsed = urlparse(url)
    except Exception:
        raise HTTPException(status_code=400, detail="URL de repositorio inválida.")
    if parsed.scheme != "https":
        raise HTTPException(status_code=400, detail="Solo se permiten URLs HTTPS.")
    if parsed.hostname not in ALLOWED_REPO_HOSTS:
        raise HTTPException(
            status_code=400,
            detail=f"Host no permitido. Usar: {', '.join(sorted(ALLOWED_REPO_HOSTS))}"
        )
    path_parts = [p for p in parsed.path.split("/") if p]
    if len(path_parts) < 2:
        raise HTTPException(
            status_code=400,
            detail="La URL debe incluir usuario y repositorio: https://github.com/usuario/repo"
        )


def _validate_branch(branch: str) -> None:
    """Previene command injection en el nombre del branch."""
    if not BRANCH_REGEX.match(branch):
        raise HTTPException(
            status_code=400,
            detail="Nombre de branch inválido. Solo se permiten letras, números, puntos, guiones y /."
        )


def _get_real_ip(request: Request) -> Optional[str]:
    """
    Extrae la IP real del cliente respetando el proxy inverso (Traefik/Nginx).
    Orden de precedencia:
      1. X-Real-IP  — cabecera canónica que Traefik/Nginx inyectan con la IP del cliente
      2. X-Forwarded-For — primer segmento (más cercano al cliente)
      3. request.client.host — fallback directo (correcto solo sin proxy)
    IMPORTANTE: solo confiar en estas cabeceras si el proxy está en una red de confianza
    y está configurado para reescribirlas (no reenviarlas desde el cliente).
    """
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else None


router = APIRouter()

DOMAIN = "hostingguard.lat"

PLANS = {
    "free":     {"cpu": "0.25", "memory": "256m",  "max_sites": 1,    "days": 14},
    "personal": {"cpu": "0.5",  "memory": "512m",  "max_sites": 1,    "days": None},
    "negocio":  {"cpu": "1",    "memory": "1g",    "max_sites": 3,    "days": None},
    "agencia":  {"cpu": "2",    "memory": "2g",    "max_sites": None, "days": None},
}


async def _verify_container_state(container_name: str, expected: str = "running", retries: int = 3, delay: float = 1.5) -> str:
    """Poll docker inspect until the container reaches `expected` state or retries are exhausted.

    Returns the final state string (e.g. 'running', 'exited', 'unknown').
    Logs a warning when the container doesn't reach the expected state.
    """
    for _ in range(retries):
        await asyncio.sleep(delay)
        code, out, _ = await run_docker_command_async(
            ["inspect", "--format", "{{.State.Status}}", container_name],
            timeout=5,
        )
        if code == 0:
            state = out.strip()
            if state == expected:
                return state
    logger.warning(
        "post-docker verification: container %s did not reach '%s' after %d retries (last=%s)",
        container_name, expected, retries, state if code == 0 else "inspect_failed",
    )
    return state if code == 0 else "unknown"


def _enforce_plan_container_limit(user_id: int, plan_name: str) -> None:
    """Raises 403 if the user has reached their plan's container quota.

    Uses the user's actual account plan (not the form-selected plan) so that
    paid users are checked against their real quota.
    """
    user_db = _user_repo.get_user_by_id(user_id)
    effective_plan = (user_db.get("plan") or plan_name) if user_db else plan_name
    plan = PLANS.get(effective_plan) or PLANS.get(plan_name)
    if not plan:
        return
    max_sites = plan.get("max_sites")
    if max_sites is None:
        return  # unlimited (agencia)
    active = hosting_repo.count_active_hostings(user_id)
    if active >= max_sites:
        try:
            notify(
                user_id,
                "Límite de plan alcanzado",
                f"Tu plan '{effective_plan}' permite {max_sites} sitio{'s' if max_sites != 1 else ''}. "
                "Eliminá un sitio existente o actualizá tu plan para crear más.",
                category="billing", severity="warning", channel="dashboard",
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=403,
            detail=f"Límite de proyectos alcanzado para el plan '{plan_name}'. "
                   f"Máximo: {max_sites}. Tienes {active} activo(s). "
                   "Elimina un sitio existente o actualiza tu plan.",
        )


MAX_FREE_USERS = 10  # Global cap — keep infra costs bounded


def _enforce_free_plan_policy(user_id: int, plan_name: str) -> None:
    """Raise 503/403 for free-plan requests that breach global or per-user limits.

    Called before any create endpoint that accepts plan='free'.
    Admins bypass all checks. Paid users bypass free-tier restrictions.
    """
    if plan_name != "free":
        return
    # Paid users are not subject to free-tier restrictions
    user_db = _user_repo.get_user_by_id(user_id)
    if user_db and user_db.get("plan", "free") != "free":
        return
    from app.observability.metrics import FREE_PLAN_REJECTIONS
    if hosting_repo.count_active_free_users() >= MAX_FREE_USERS:
        FREE_PLAN_REJECTIONS.labels(reason="global_cap").inc()
        raise HTTPException(
            status_code=503,
            detail="Free tier capacity reached. Please upgrade to continue.",
        )
    if hosting_repo.had_free_hosting_recently(user_id):
        FREE_PLAN_REJECTIONS.labels(reason="recent_history").inc()
        raise HTTPException(
            status_code=403,
            detail="Ya tuviste un sitio en plan free en los últimos 30 días. "
                   "Actualiza tu plan para crear uno nuevo.",
        )


class CreateHostingRequest(BaseModel):
    name: str
    plan: str


@router.post("/create-hosting")
@limiter.limit("3/minute")
async def create_hosting(data: CreateHostingRequest, request: Request, user: dict = Depends(verify_token)):
    try:
        # Block unverified emails — prevents free-trial abuse with disposable addresses
        _uid = user.get("user_id")
        user_db = _user_repo.get_user_by_id(int(_uid)) if _uid is not None else None
        if user_db and not user_db.get("email_verified", 1):
            raise HTTPException(
                status_code=403,
                detail="email_not_verified",
            )

        # FIX #7: validar nombre antes de usarlo en subdominios y labels
        _validate_project_name(data.name)

        user_id      = user.get("user_id")
        project_name = data.name.lower().replace(" ", "-")
        subdomain    = f"{project_name}.{DOMAIN}"
        container_name = f"user_{user_id}_{project_name}_{uuid.uuid4().hex[:6]}"
        ip_address   = _get_real_ip(request)

        plan = PLANS.get(data.plan)
        if not plan:
            raise HTTPException(status_code=400, detail="plan inválido")

        # Verificar que el plan solicitado coincide con el plan adquirido.
        # Impide que un usuario free solicite recursos de un plan de pago.
        if data.plan != "free" and user.get("role") != "admin":
            user_db = _user_repo.get_user_by_id(user_id)
            user_plan = user_db.get("plan", "free") if user_db else "free"
            if user_plan != data.plan:
                raise HTTPException(
                    status_code=403,
                    detail=f"Tu plan actual es '{user_plan}'. Actualiza tu suscripción para usar el plan '{data.plan}'."
                )

        if data.plan == "free" and ip_address:
            if hosting_repo.has_free_plan_from_ip(ip_address):
                raise HTTPException(
                    status_code=403,
                    detail="Solo se permite un alojamiento en plan free por dirección IP. Por favor, actualiza tu plan."
                )

        if user.get("role") != "admin" and user_id is not None:
            _enforce_free_plan_policy(int(user_id), data.plan)
            _enforce_plan_container_limit(int(user_id), data.plan)

        image = "nginx:alpine"

        host_site_dir = f"/opt/clients/{container_name}"
        os.makedirs(host_site_dir, exist_ok=True)

        # Provisioning gate: ensure index.html exists before starting the container.
        # Without it, nginx serves an empty directory and returns 403 Forbidden.
        placeholder_index = os.path.join(host_site_dir, "index.html")
        if not os.path.exists(placeholder_index):
            with open(placeholder_index, "w", encoding="utf-8") as _f:
                _f.write(
                    "<!DOCTYPE html><html lang='es'><head><meta charset='UTF-8'>"
                    "<title>Sitio en configuración — HostingGuard</title></head><body>"
                    "<h1>Sitio en configuración</h1>"
                    "<p>Sube tu contenido desde el panel de HostingGuard.</p>"
                    "</body></html>"
                )

        command = [
            "run", "-d",
            "--name",     container_name,
            "--network",  "deploy_hosting_network",
            "--restart",  "unless-stopped",
            # FIX #7: aplicar límites de recursos del plan (antes faltaban en este endpoint)
            "--cpus",     plan["cpu"],
            "--memory",   plan["memory"],
            "-v", f"{host_site_dir}:/usr/share/nginx/html:ro",
            "-l", "traefik.enable=true",
            "-l", f"traefik.http.routers.{container_name}.rule=Host(`{subdomain}`)",
            "-l", f"traefik.http.routers.{container_name}.entrypoints=websecure",
            "-l", f"traefik.http.routers.{container_name}.tls.certresolver=le",
            "-l", f"traefik.http.routers.{container_name}.middlewares=hg-forwardauth",
            "-l", f"traefik.http.services.{container_name}.loadbalancer.server.port=80",
            image
        ]

        code, _, stderr = await run_docker_command_async(command, timeout=30)

        if code != 0:
            raise HTTPException(status_code=500, detail=f"Docker error: {stderr}")

        hosting_id = hosting_repo.create_hosting(
            user_id=user_id,
            name=data.name,
            subdomain=subdomain,
            container_name=container_name,
            plan=data.plan,
            ip_address=ip_address
        )

        # ── Provisioning Gate ────────────────────────────────────────────────
        # Create Traefik File Provider YAML (official routing model)
        try:
            from app.services.traefik_file_provider import create_tenant_file_provider
            create_tenant_file_provider(hosting_id, container_name, subdomain)
        except Exception as _fp_exc:
            logger.warning(
                "create_hosting: file provider creation failed for hosting_id=%s: %s",
                hosting_id, _fp_exc,
            )

        # Run provisioning gate (skip HTTP checks — cert/routing not ready yet)
        _gate_status = "active_with_placeholder"
        _gate_reason = "gate not run"
        try:
            from app.services.provisioning_gate import validate_static_tenant_provisioning
            _gate_result = validate_static_tenant_provisioning(
                hosting_id, container_name, subdomain, check_http=False
            )
            _gate_status = _gate_result.status
            _gate_reason = _gate_result.reason
        except Exception as _gate_exc:
            logger.warning(
                "create_hosting: provisioning gate failed for hosting_id=%s: %s",
                hosting_id, _gate_exc,
            )

        # Update hosting status to provisioning gate result (DB was set to 'active' by default)
        if _gate_status != "active":
            try:
                hosting_repo.update_hosting_status(hosting_id, _gate_status)
            except Exception as _upd_exc:
                logger.warning(
                    "create_hosting: status update failed for hosting_id=%s: %s",
                    hosting_id, _upd_exc,
                )

        try:
            from app.services.activity_service import log_event as _log
            _log(
                user_id=user_id, hosting_id=hosting_id,
                event_type=(
                    "hosting.provisioning.gate_passed"
                    if _gate_status in ("active", "active_with_placeholder")
                    else "hosting.provisioning.gate_failed"
                ),
                category="hosting",
                severity="info" if _gate_status in ("active", "active_with_placeholder") else "warning",
                title=f"Provisioning gate: {_gate_status}",
                message=_gate_reason,
                source="provisioning",
            )
        except Exception:
            pass
        # ── end Provisioning Gate ────────────────────────────────────────────

        notify(
            user_id or 0,
            f"Sitio creado: {data.name}",
            f"Tu sitio '{data.name}' está activo en https://{subdomain}",
            category="hosting", severity="success", channel="both",
            action_url="/dashboard",
        )
        try:
            from app.services.activity_service import log_event as _log
            _log(user_id=user_id, hosting_id=hosting_id, event_type="hosting_created",
                 category="hosting", title=f"Sitio creado: {data.name}",
                 message=f"Plan: {data.plan}, URL: https://{subdomain}",
                 ip=ip_address, source="dashboard")
        except Exception:
            pass

        return {
            "status":              "created",
            "provisioning_status": _gate_status,
            "hosting_id":          hosting_id,
            "user_id":             user_id,
            "url":                 f"https://{subdomain}",
            "container":           container_name,
        }

    except HTTPException:
        raise
    except Exception as e:
        try:
            notify(
                user.get("user_id") or 0,
                f"Error al crear sitio: {data.name}",
                f"No se pudo crear el sitio '{data.name}'. Nuestro equipo fue notificado.",
                category="hosting", severity="critical", channel="dashboard",
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))


from app.services.hosting.list_service import list_hostings

router.get("/list-hostings")(list_hostings)



async def _do_delete_hosting(hosting_id: int, user_id: int) -> dict:
    """
    Delete a hosting owned by user_id.

    Steps:
      1. docker rm -f WP container + DB container (idempotent: 'No such container' = ok)
      2. Verify with docker inspect that both containers are actually gone
      3. If any container survives → raise 500, do NOT touch the DB
      4. delete_hosting: hard-delete all child records + remove hosting row
    """
    hosting = hosting_repo.get_hosting(hosting_id, user_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting not found")

    if hosting.get("status") == "deleted":
        return {"status": "deleted", "hosting_id": hosting_id, "note": "already_deleted"}

    container_name = hosting["container_name"]
    db_container   = container_name.replace("_wp_", "_db_", 1) if "_wp_" in container_name else None
    targets        = [container_name] + ([db_container] if db_container else [])

    # ── 1. Remove containers ─────────────────────────────────────────────────
    docker_errors = []
    for cname in targets:
        code, _, stderr = await run_docker_command_async(["rm", "-f", cname], timeout=15)
        if code != 0 and "No such container" not in stderr:
            err = stderr.strip()[:160]
            docker_errors.append(f"{cname}: {err}")
            logger.error("delete_hosting docker rm -f %s failed (code=%d): %s", cname, code, err)

    # ── 2. Post-delete verification ──────────────────────────────────────────
    surviving = []
    for cname in targets:
        code, _, _ = await run_docker_command_async(
            ["inspect", "--format", "{{.Name}}", cname], timeout=5
        )
        if code == 0:
            surviving.append(cname)

    if surviving:
        detail = (
            f"No se pudo eliminar el hosting. "
            f"Containers activos: {', '.join(surviving)}. "
            "Usá 'Force Cleanup' desde el panel de administración."
        )
        if docker_errors:
            detail += f" Docker errors: {'; '.join(docker_errors)}"
        raise HTTPException(status_code=500, detail=detail)

    # ── 2.5. Remove Traefik File Provider YAML (non-fatal) ──────────────────────
    try:
        from app.services.traefik_file_provider import delete_tenant_file_provider
        delete_tenant_file_provider(hosting_id)
    except Exception as _fp_exc:
        logger.warning(
            "delete_hosting: file provider cleanup failed for hosting_id=%s: %s",
            hosting_id, _fp_exc,
        )

    # ── 3. Hard-delete: cascade-clean all child records + remove hosting row ────
    site_name = hosting.get("name") or str(hosting_id)
    hosting_repo.delete_hosting(hosting_id, user_id, db_container=db_container)
    logger.info(
        "hosting_deleted hosting_id=%s container=%s db_container=%s",
        hosting_id, container_name, db_container,
    )
    notify(
        user_id or 0,
        f"Sitio eliminado: {site_name}",
        f"El sitio '{site_name}' fue eliminado correctamente.",
        category="hosting", severity="info", channel="both",
    )

    # ── 4. Invalidate the Redis list cache for this user ─────────────────────
    try:
        from app.infra.redis_client import get_redis
        r = get_redis()
        if r is not None:
            pattern = f"hg:list:{user_id}:*"
            keys = r.keys(pattern)
            if keys:
                r.delete(*keys)
    except Exception:
        pass

    try:
        from app.services.activity_service import log_event as _log
        _log(user_id=user_id, hosting_id=hosting_id, event_type="hosting_deleted",
             category="hosting", severity="warning",
             title=f"Sitio eliminado: {site_name}",
             source="dashboard")
    except Exception:
        pass

    # Remove residual client directory (non-fatal, path traversal guard)
    _OPT_CLIENTS = "/opt/clients"
    _safe_base   = os.path.realpath(_OPT_CLIENTS)
    _candidate   = os.path.realpath(os.path.join(_OPT_CLIENTS, container_name))
    if not _candidate.startswith(_safe_base + os.sep):
        logger.warning("hosting_deleted: path traversal blocked for container %r", container_name)
    elif os.path.isdir(_candidate):
        try:
            shutil.rmtree(_candidate)
            logger.info("hosting_deleted: removed client dir %s", _candidate)
        except Exception as exc:
            logger.warning("hosting_deleted: could not remove %s: %s", _candidate, exc)

    return {"status": "deleted", "hosting_id": hosting_id}


@router.delete("/hosting/{hosting_id}")
async def delete_hosting_rest(hosting_id: int, user: dict = Depends(require_support_write)):
    """RESTful DELETE — used by the dashboard frontend."""
    user_id: int = int(user["user_id"])
    return await _do_delete_hosting(hosting_id, user_id)


@router.delete("/delete-hosting/{hosting_id}")
async def delete_hosting(hosting_id: int, user: dict = Depends(require_support_write)):
    """Legacy route — kept for backwards compatibility."""
    user_id: int = int(user["user_id"])
    return await _do_delete_hosting(hosting_id, user_id)

class _TerminateRequest(BaseModel):
    reason: str
    description: Optional[str] = None


@router.post("/hostings/{hosting_id}/terminate")
@limiter.limit("3/hour")
async def terminate_hosting_by_user(
    hosting_id: int,
    request: Request,
    body: _TerminateRequest,
    user: dict = Depends(verify_token),
):
    """
    User-initiated hosting termination.

    Cleans up custom domain Traefik configs, removes domain DB records,
    then hard-deletes containers + hosting row.
    """
    user_id: int = int(user["user_id"])

    # ── 1. Clean up custom domains ───────────────────────────────────────────
    try:
        from app.infra.audit.domain_repository import DomainRepository
        from app.services.domain_checker import remove_traefik_config
        domain_repo = DomainRepository()
        domains = domain_repo.get_domains(hosting_id, user_id)
        for d in domains:
            try:
                remove_traefik_config(d["domain_id"])
            except Exception:
                pass
            try:
                domain_repo.delete_domain(d["domain_id"], user_id)
            except Exception:
                pass
    except Exception as exc:
        logger.warning("terminate_hosting: domain cleanup error for hosting %s: %s", hosting_id, exc)

    # ── 2. Log reason before deletion (hosting row disappears after) ─────────
    try:
        from app.services.activity_service import log_event as _log
        hosting_pre = hosting_repo.get_hosting(hosting_id, user_id)
        site_name = (hosting_pre or {}).get("name") or str(hosting_id)
        full_reason = body.reason
        if body.description:
            full_reason += f" — {body.description}"
        _log(
            user_id=user_id, hosting_id=hosting_id,
            event_type="hosting_termination_requested",
            category="hosting", severity="warning",
            title=f"Solicitud de eliminación: {site_name}",
            message=full_reason,
            source="dashboard",
        )
    except Exception:
        pass

    # ── 3. Delete containers + hosting row ───────────────────────────────────
    return await _do_delete_hosting(hosting_id, user_id)


@router.post("/hostings/{hosting_id}/restart")
@limiter.limit("3/minute")
async def restart_hosting(hosting_id: int, request: Request, user: dict = Depends(verify_token), _cap: None = Depends(docker_capacity)):
    user_id = user.get("user_id")
    hosting = hosting_repo.get_hosting(hosting_id, user_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting not found")
    name = hosting["container_name"]
    lock = await container_lock(name)
    if lock.locked():
        raise HTTPException(status_code=409, detail="Operación en progreso para este hosting. Intenta en unos segundos.")
    async with lock:
        async with docker_op("restart"):
            code, _, stderr = await run_docker_command_async(["restart", name], timeout=20)
            if code != 0:
                logger.error(
                    "docker_op_failed",
                    extra={"operation": "restart", "container": name,
                           "returncode": code, "stderr": stderr},
                )
            final_state = await _verify_container_state(name, expected="running")
    notify(
        user_id or 0,
        f"Sitio reiniciado: {hosting.get('name') or hosting_id}",
        f"El sitio '{hosting.get('name') or hosting_id}' fue reiniciado.",
        category="hosting", severity="info", channel="both",
        action_url="/dashboard",
    )
    from app.services.activity_service import log_event as _log
    _log(user_id=user_id, hosting_id=hosting_id, event_type="hosting_restarted",
         category="hosting", title=f"Sitio reiniciado: {hosting.get('name') or hosting_id}",
         ip=request.client.host if request.client else None, source="dashboard")
    return {"status": "restarting", "container_state": final_state}


@router.post("/hostings/{hosting_id}/stop")
@limiter.limit("5/minute")
async def stop_hosting(hosting_id: int, request: Request, user: dict = Depends(verify_token), _cap: None = Depends(docker_capacity)):
    user_id = user.get("user_id")
    hosting = hosting_repo.get_hosting(hosting_id, user_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting not found")
    name = hosting["container_name"]
    lock = await container_lock(name)
    if lock.locked():
        raise HTTPException(status_code=409, detail="Operación en progreso para este hosting. Intenta en unos segundos.")
    async with lock:
        async with docker_op("stop"):
            code, _, stderr = await run_docker_command_async(["stop", name], timeout=20)
            if code != 0:
                logger.error(
                    "docker_op_failed",
                    extra={"operation": "stop", "container": name,
                           "returncode": code, "stderr": stderr},
                )
    notify(
        user_id or 0,
        f"Sitio detenido: {hosting.get('name') or hosting_id}",
        f"El sitio '{hosting.get('name') or hosting_id}' fue detenido.",
        category="hosting", severity="warning", channel="both",
        action_url="/dashboard",
    )
    from app.services.activity_service import log_event as _log
    _log(user_id=user_id, hosting_id=hosting_id, event_type="hosting_stopped",
         category="hosting", severity="warning",
         title=f"Sitio detenido: {hosting.get('name') or hosting_id}",
         ip=request.client.host if request.client else None, source="dashboard")
    return {"status": "stopped"}


@router.post("/hostings/{hosting_id}/start")
@limiter.limit("5/minute")
async def start_hosting(hosting_id: int, request: Request, user: dict = Depends(verify_token), _cap: None = Depends(docker_capacity)):
    user_id = user.get("user_id")
    hosting = hosting_repo.get_hosting(hosting_id, user_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting not found")
    name = hosting["container_name"]
    lock = await container_lock(name)
    if lock.locked():
        raise HTTPException(status_code=409, detail="Operación en progreso para este hosting. Intenta en unos segundos.")
    async with lock:
        async with docker_op("start"):
            code, _, stderr = await run_docker_command_async(["start", name], timeout=20)
            if code != 0:
                logger.error(
                    "docker_op_failed",
                    extra={"operation": "start", "container": name,
                           "returncode": code, "stderr": stderr},
                )
            final_state = await _verify_container_state(name, expected="running")
    notify(
        user_id or 0,
        f"Sitio iniciado: {hosting.get('name') or hosting_id}",
        f"El sitio '{hosting.get('name') or hosting_id}' fue iniciado correctamente.",
        category="hosting", severity="success", channel="both",
        action_url="/dashboard",
    )
    from app.services.activity_service import log_event as _log
    _log(user_id=user_id, hosting_id=hosting_id, event_type="hosting_started",
         category="hosting", title=f"Sitio iniciado: {hosting.get('name') or hosting_id}",
         ip=request.client.host if request.client else None, source="dashboard")
    return {"status": "starting", "container_state": final_state}

from app.services.hosting.logs_service import get_hosting_logs

router.get("/hostings/{hosting_id}/logs")(get_hosting_logs)



from app.services.hosting.metrics_service import get_hosting_metrics

router.get("/hostings/{hosting_id}/metrics")(get_hosting_metrics)


@router.post("/create-wordpress")
async def create_wordpress(data: CreateHostingRequest, request: Request, user: dict = Depends(verify_token)):
    try:
        # FIX #7: validar nombre
        _validate_project_name(data.name)

        user_id      = user.get("user_id")
        project_name = data.name.lower().replace(" ", "-")
        subdomain    = f"{project_name}.{DOMAIN}"
        uid          = uuid.uuid4().hex[:6]
        ip_address   = _get_real_ip(request)

        # FIX #2: convención de nombres clara para poder limpiar el DB container al borrar
        db_container = f"user_{user_id}_db_{project_name}_{uid}"
        wp_container = f"user_{user_id}_wp_{project_name}_{uid}"
        network      = "deploy_hosting_network"

        # Always use the user's actual account plan — never trust the form-submitted plan.
        # This prevents paid users from creating 'free' containers.
        if user.get("role") != "admin" and user_id is not None:
            user_db = _user_repo.get_user_by_id(int(user_id))
            effective_plan_name = (user_db.get("plan") or "free") if user_db else "free"
        else:
            effective_plan_name = data.plan  # admin can specify any plan

        plan = PLANS.get(effective_plan_name)
        if not plan:
            raise HTTPException(status_code=400, detail="plan inválido")

        if effective_plan_name == "free" and ip_address:
            if hosting_repo.has_free_plan_from_ip(ip_address):
                raise HTTPException(
                    status_code=403,
                    detail="Solo se permite un alojamiento en plan free por dirección IP. Por favor, actualiza tu plan."
                )

        if user.get("role") != "admin" and user_id is not None:
            _enforce_free_plan_policy(int(user_id), effective_plan_name)
            _enforce_plan_container_limit(int(user_id), effective_plan_name)

        # FIX #9: la contraseña se genera y se pasa a ambos contenedores correctamente
        # (el patrón de nombres garantiza que delete_hosting pueda limpiar db_container)
        db_password = uuid.uuid4().hex[:16]

        # 1. Lanzar MariaDB
        db_cmd = [
            "run", "-d",
            "--name",    db_container,
            "--network", network,
            "--restart", "unless-stopped",
            "-e", f"MYSQL_ROOT_PASSWORD={db_password}",
            "-e", "MYSQL_DATABASE=wordpress",
            "-e", "MYSQL_USER=wpuser",
            "-e", f"MYSQL_PASSWORD={db_password}",
            "--cpus",   plan["cpu"],
            "--memory", plan["memory"],
            "mariadb:10.11"
        ]
        db_code, _, db_err = await run_docker_command_async(db_cmd, timeout=30)
        if db_code != 0:
            raise HTTPException(status_code=500, detail=f"MySQL error: {db_err}")

        # 2. Lanzar WordPress
        wp_cmd = [
            "run", "-d",
            "--name",    wp_container,
            "--network", network,
            "--restart", "unless-stopped",
            "-e", f"WORDPRESS_DB_HOST={db_container}",
            "-e", "WORDPRESS_DB_USER=wpuser",
            "-e", f"WORDPRESS_DB_PASSWORD={db_password}",
            "-e", "WORDPRESS_DB_NAME=wordpress",
            "--cpus",   plan["cpu"],
            "--memory", plan["memory"],
            "-l", "traefik.enable=true",
            "-l", f"traefik.http.routers.{wp_container}.rule=Host(`{subdomain}`)",
            "-l", f"traefik.http.routers.{wp_container}.entrypoints=websecure",
            "-l", f"traefik.http.routers.{wp_container}.tls.certresolver=le",
            "-l", f"traefik.http.routers.{wp_container}.middlewares=hg-forwardauth",
            "-l", f"traefik.http.services.{wp_container}.loadbalancer.server.port=80",
            "hostingguard/wordpress:latest"
        ]
        wp_code, _, wp_err = await run_docker_command_async(wp_cmd, timeout=30)
        if wp_code != 0:
            # Rollback: limpiar db container si WordPress falla
            await run_docker_command_async(["rm", "-f", db_container], timeout=15)
            raise HTTPException(status_code=500, detail=f"WordPress error: {wp_err}")

        # 3. Persistir en DB
        # NOTA: solo se guarda wp_container. El db_container se recupera por convención
        # de nombres (_wp_ → _db_) en delete_hosting. Ver FIX #2.
        hosting_id = hosting_repo.create_hosting(
            user_id=user_id,
            name=data.name,
            subdomain=subdomain,
            container_name=wp_container,
            plan=effective_plan_name,
            ip_address=ip_address
        )

        # Generate WordPress admin credentials and persist them before background task.
        wp_admin_pass = secrets.token_urlsafe(12)
        hosting_repo.set_wp_credentials(hosting_id, wp_admin_pass)

        user_email = user.get("email", "")

        # Run optimization in background — WP needs ~60s to initialize before WP-CLI works.
        loop = asyncio.get_running_loop()
        _uid = user_id or 0
        _sname = data.name
        loop.run_in_executor(
            None,
            lambda: optimize_wordpress(
                wp_container,
                log=lambda msg: logger.info("[wp_new:%s] %s", wp_container, msg),
                auto_install=True,
                install_url=f"https://{subdomain}",
                install_title=_sname,
                install_email=user_email,
                admin_password=wp_admin_pass,
                user_id=_uid,
                site_name=_sname,
            ),
        )

        notify(
            user_id or 0,
            f"WordPress creado: {data.name}",
            f"Tu sitio WordPress '{data.name}' está siendo configurado. "
            f"Estará disponible en https://{subdomain} en 30-60 segundos.",
            category="wordpress", severity="success", channel="both",
            action_url="/dashboard",
        )

        return {
            "status":       "created",
            "type":         "wordpress",
            "hosting_id":   hosting_id,
            "url":          f"https://{subdomain}",
            "container":    wp_container,
            "db_container": db_container,
            "note":         "WordPress estará listo en 30-60 segundos"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class GitDeployRequest(BaseModel):
    name:             str
    plan:             str
    repo_url:         str
    branch:           str = "main"
    root_directory:   str = ""          # subdirectory to serve/run from inside the cloned repo
    install_command:  Optional[str] = None  # overrides default 'npm install' / 'pip install -r requirements.txt'
    build_command:    Optional[str] = None  # overrides default 'npm run build'
    start_command:    Optional[str] = None  # set for backend apps: 'uvicorn app.main:app --host 0.0.0.0 --port 8000'
    output_directory: Optional[str] = None  # where built assets live; overrides dist/build auto-detect
    port:             int = 80              # container port Traefik forwards to
    framework:        Optional[str] = None  # explicit: 'static' | 'node' | 'python' | 'dockerfile'
    dockerfile_path:  Optional[str] = None  # path relative to root_directory
    env_vars:         dict = {}             # { KEY: value } — injected at runtime

    @field_validator("repo_url", "branch", "name", mode="before")
    @classmethod
    def _strip_str(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v


ENV_KEY_RE = re.compile(r'^[A-Z_][A-Z0-9_]{0,63}$')


def _validate_env_vars(env_vars: dict) -> None:
    for k in env_vars:
        if not ENV_KEY_RE.match(str(k)):
            raise HTTPException(status_code=400, detail=f"Env var key inválida: {k!r}")



@router.post("/deploy-from-github")
@limiter.limit(DEPLOY_RATE_LIMIT)
async def deploy_from_github(data: GitDeployRequest, request: Request, user: dict = Depends(verify_token)):
    _validate_project_name(data.name)
    _validate_repo_url(data.repo_url)
    _validate_branch(data.branch)
    _validate_env_vars(data.env_vars)

    user_id      = user.get("user_id")
    project_name = data.name.lower().replace(" ", "-")
    subdomain    = f"{project_name}.{DOMAIN}"
    uid          = uuid.uuid4().hex[:6]
    container_name = f"user_{user_id}_git_{project_name}_{uid}"
    ip_address   = _get_real_ip(request)

    plan = PLANS.get(data.plan)
    if not plan:
        raise HTTPException(status_code=400, detail="Plan inválido")

    if data.plan != "free" and user.get("role") != "admin":
        user_db   = _user_repo.get_user_by_id(user_id)
        user_plan = user_db.get("plan", "free") if user_db else "free"
        if user_plan != data.plan:
            raise HTTPException(
                status_code=403,
                detail=f"Tu plan actual es '{user_plan}'. Actualiza tu suscripción para usar el plan '{data.plan}'."
            )

    if data.plan == "free" and ip_address:
        if hosting_repo.has_free_plan_from_ip(ip_address):
            raise HTTPException(
                status_code=403,
                detail="Solo se permite un alojamiento en plan free por dirección IP. Por favor, actualiza tu plan."
            )

    if user.get("role") != "admin" and user_id is not None:
        _enforce_free_plan_policy(int(user_id), data.plan)
        _enforce_plan_container_limit(int(user_id), data.plan)

    try:
        return await run_github_deploy(
            data=data,
            user_id=user_id,
            ip_address=ip_address,
            project_name=project_name,
            subdomain=subdomain,
            container_name=container_name,
            plan=plan,
        )
    except DeployError as de:
        return JSONResponse(
            status_code=de.status_code,
            content=de.to_dict(request_id=request.headers.get("X-Request-ID")),
        )



@router.post("/hostings/{hosting_id}/redeploy")
@limiter.limit(DEPLOY_RATE_LIMIT)
async def redeploy_from_github(hosting_id: int, request: Request, user: dict = Depends(verify_token)):
    user_id    = user.get("user_id")
    hosting    = hosting_repo.get_hosting(hosting_id, user_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting not found")

    container_name = hosting["container_name"]
    site_dir       = f"/opt/clients/{container_name}"

    if not os.path.exists(site_dir):
        raise HTTPException(status_code=400, detail="No es un deploy de GitHub")
    if not os.path.exists(os.path.join(site_dir, ".git")):
        raise HTTPException(status_code=400, detail="El directorio no contiene un repositorio Git válido.")

    cfg_row        = hosting_repo.get_git_config(hosting_id, user_id) or {}
    git_config     = cfg_row.get("git_config") or {}
    root_directory = git_config.get("root_directory", "")
    work_dir       = os.path.join(site_dir, root_directory) if root_directory else site_dir
    branch         = git_config.get("branch", "main")
    loop           = asyncio.get_running_loop()
    deploy_log     = {"started_at": datetime.now().isoformat(), "stages": {}}

    pull = await loop.run_in_executor(
        None,
        lambda: subprocess.run(
            ["git", "-C", site_dir, "pull", "origin", branch],
            capture_output=True, text=True, timeout=60
        )
    )
    deploy_log["stages"]["pull"] = {
        "ok": pull.returncode == 0,
        "stdout": pull.stdout[-2000:],
        "stderr": pull.stderr[-2000:],
    }
    if pull.returncode != 0:
        raise HTTPException(status_code=500, detail=f"git pull failed: {pull.stderr[-500:]}")

    strategy = git_config.get("strategy", "")

    if git_config.get("dockerfile_path") or git_config.get("framework") == "dockerfile":
        df_path   = git_config.get("dockerfile_path") or "Dockerfile"
        image_tag = container_name
        build_result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                ["docker", "build", "-f", os.path.join(work_dir, df_path), "-t", image_tag, work_dir],
                capture_output=True, text=True, timeout=300
            )
        )
        deploy_log["stages"]["build"] = {
            "ok": build_result.returncode == 0,
            "stderr": build_result.stderr[-3000:],
        }
        if build_result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Docker build error: {build_result.stderr[-500:]}")

        await run_docker_command_async(["stop", container_name], timeout=30)
        await run_docker_command_async(["rm",   container_name], timeout=10)

        plan_cfg  = PLANS.get(hosting.get("plan", "free"), PLANS["free"])
        env_vars  = git_config.get("env_vars", {})
        port      = int(git_config.get("port", 80))
        subdomain = hosting.get("subdomain", "")
        command = [
            "run", "-d",
            "--name",    container_name,
            "--network", "deploy_hosting_network",
            "--restart", "unless-stopped",
            "--cpus",    plan_cfg["cpu"],
            "--memory",  plan_cfg["memory"],
            *_docker_env_flags(env_vars),
            *_traefik_labels(container_name, subdomain, port),
            image_tag,
        ]
        code, _, stderr = await run_docker_command_async(command, timeout=60)
        deploy_log["stages"]["container"] = {"ok": code == 0, "stderr": stderr[-2000:]}
        if code != 0:
            raise HTTPException(status_code=500, detail=f"Docker run error: {stderr[-500:]}")

    elif strategy == "static_built":
        # Node build strategy: re-run build with the same commands, then restart nginx
        install_cmd = git_config.get("install_command") or "npm install"
        build_cmd   = git_config.get("build_command")   or "npm run build"
        env_vars    = git_config.get("env_vars", {})
        _build_run  = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                ["docker", "run", "--rm",
                 "-v", f"{work_dir}:/app",
                 "-w", "/app",
                 *_docker_env_flags(env_vars),
                 "node:20-alpine",
                 "sh", "-c", f"{install_cmd} && {build_cmd}"],
                capture_output=True, text=True, timeout=300
            )
        )
        deploy_log["stages"]["build"] = {
            "ok":     _build_run.returncode == 0,
            "stderr": _build_run.stderr[-3000:],
        }
        if _build_run.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Build error: {_build_run.stderr[-500:]}")
        code, _, stderr = await run_docker_command_async(["restart", container_name], timeout=30)
        deploy_log["stages"]["container"] = {"ok": code == 0, "stderr": stderr[-2000:]}
        if code != 0:
            raise HTTPException(status_code=500, detail=f"Docker restart error: {stderr[-500:]}")

    else:
        # server (Strategy B) or pure static: git pull already updated files; restart is enough
        code, _, stderr = await run_docker_command_async(["restart", container_name], timeout=30)
        deploy_log["stages"]["container"] = {"ok": code == 0, "stderr": stderr[-2000:]}
        if code != 0:
            raise HTTPException(status_code=500, detail=f"Docker restart error: {stderr[-500:]}")

    deploy_log["finished_at"] = datetime.now().isoformat()
    try:
        hosting_repo.append_deploy_log(hosting_id, deploy_log)
    except Exception:
        pass

    return {"status": "redeployed", "git_output": pull.stdout, "container": container_name}


@router.post("/hostings/{hosting_id}/webhook")
async def github_webhook(hosting_id: int, request: Request):
    """GitHub webhook endpoint — validates HMAC and triggers redeploy."""
    import hmac as _hmac
    import hashlib as _hashlib

    body = await request.body()
    sig_header = request.headers.get("X-Hub-Signature-256", "")

    hosting = hosting_repo.get_for_webhook(hosting_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting not found")

    webhook_token = hosting.get("webhook_token") or ""
    if not webhook_token:
        raise HTTPException(status_code=400, detail="Webhook no configurado para este hosting")

    expected = "sha256=" + _hmac.new(
        webhook_token.encode(), body, _hashlib.sha256
    ).hexdigest()
    if not _hmac.compare_digest(expected, sig_header):
        raise HTTPException(status_code=401, detail="Firma inválida")

    # Only redeploy on push events
    event_type = request.headers.get("X-GitHub-Event", "")
    if event_type != "push":
        return {"status": "ignored", "event": event_type}

    git_config     = hosting.get("git_config") or {}
    container_name = hosting["container_name"]
    site_dir       = f"/opt/clients/{container_name}"
    root_directory = git_config.get("root_directory", "")
    work_dir       = os.path.join(site_dir, root_directory) if root_directory else site_dir
    branch         = git_config.get("branch", "main")
    loop           = asyncio.get_running_loop()
    deploy_log     = {"started_at": datetime.now().isoformat(), "stages": {}, "triggered_by": "webhook"}

    if not os.path.exists(site_dir) or not os.path.exists(os.path.join(site_dir, ".git")):
        raise HTTPException(status_code=400, detail="No es un deploy de GitHub")

    pull = await loop.run_in_executor(
        None,
        lambda: subprocess.run(
            ["git", "-C", site_dir, "pull", "origin", branch],
            capture_output=True, text=True, timeout=60
        )
    )
    deploy_log["stages"]["pull"] = {"ok": pull.returncode == 0, "stdout": pull.stdout[-2000:]}
    if pull.returncode != 0:
        try:
            hosting_repo.append_deploy_log(hosting_id, deploy_log)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"git pull failed: {pull.stderr[-500:]}")

    strategy = git_config.get("strategy", "")

    if git_config.get("dockerfile_path") or git_config.get("framework") == "dockerfile":
        df_path   = git_config.get("dockerfile_path") or "Dockerfile"
        image_tag = container_name
        build_result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                ["docker", "build", "-f", os.path.join(work_dir, df_path), "-t", image_tag, work_dir],
                capture_output=True, text=True, timeout=300
            )
        )
        deploy_log["stages"]["build"] = {"ok": build_result.returncode == 0}
        if build_result.returncode == 0:
            await run_docker_command_async(["stop", container_name], timeout=30)
            await run_docker_command_async(["rm",   container_name], timeout=10)
            plan_cfg  = PLANS.get(hosting.get("plan", "free"), PLANS["free"])
            env_vars  = git_config.get("env_vars", {})
            port      = int(git_config.get("port", 80))
            subdomain = hosting.get("subdomain", "")
            command = [
                "run", "-d",
                "--name",    container_name,
                "--network", "deploy_hosting_network",
                "--restart", "unless-stopped",
                "--cpus",    plan_cfg["cpu"],
                "--memory",  plan_cfg["memory"],
                *_docker_env_flags(env_vars),
                *_traefik_labels(container_name, subdomain, port),
                image_tag,
            ]
            code, _, _ = await run_docker_command_async(command, timeout=60)
            deploy_log["stages"]["container"] = {"ok": code == 0}

    elif strategy == "static_built":
        install_cmd = git_config.get("install_command") or "npm install"
        build_cmd   = git_config.get("build_command")   or "npm run build"
        env_vars    = git_config.get("env_vars", {})
        _build_run  = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                ["docker", "run", "--rm",
                 "-v", f"{work_dir}:/app",
                 "-w", "/app",
                 *_docker_env_flags(env_vars),
                 "node:20-alpine",
                 "sh", "-c", f"{install_cmd} && {build_cmd}"],
                capture_output=True, text=True, timeout=300
            )
        )
        deploy_log["stages"]["build"] = {"ok": _build_run.returncode == 0}
        if _build_run.returncode == 0:
            code, _, _ = await run_docker_command_async(["restart", container_name], timeout=30)
            deploy_log["stages"]["container"] = {"ok": code == 0}
        else:
            deploy_log["stages"]["container"] = {"ok": False, "error": "build failed, nginx not restarted"}

    else:
        code, _, _ = await run_docker_command_async(["restart", container_name], timeout=30)
        deploy_log["stages"]["container"] = {"ok": code == 0}

    deploy_log["finished_at"] = datetime.now().isoformat()
    try:
        hosting_repo.append_deploy_log(hosting_id, deploy_log)
    except Exception:
        pass

    return {"status": "ok"}


@router.get("/deploy-events/me")
def get_my_deploy_events(
    limit: int = 20,
    user: dict = Depends(verify_token),
):
    """Return the authenticated user's recent deploy_events (newest first)."""
    from app.infra.db import get_connection, release_connection
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT deploy_event_id, repo_url, branch, project_name,
                   stage, status, code, message, suggested_fix,
                   evidence, cleanup_status, created_at
              FROM deploy_events
             WHERE user_id = %s
             ORDER BY created_at DESC
             LIMIT %s
            """,
            (user["user_id"], min(limit, 100)),
        )
        return {"items": [dict(r) for r in cur.fetchall()]}
    finally:
        release_connection(conn)


@router.get("/hostings/{hosting_id}/deploy-logs")
def get_deploy_logs(hosting_id: int, user: dict = Depends(verify_token)):
    user_id = user.get("user_id")
    hosting = hosting_repo.get_hosting(hosting_id, user_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting not found")
    return hosting_repo.get_deploy_logs(hosting_id, user_id)

@router.post("/hostings/{hosting_id}/upload-zip")
@limiter.limit("5/hour")
async def upload_zip(
    hosting_id: int,
    request: Request,
    file: UploadFile = File(...),
    user: dict = Depends(verify_token)
):
    """
    Opción C — ZIP upload.
    El cliente sube un .zip con su sitio; el sistema lo extrae y despliega
    en el contenedor Nginx del hosting sin reiniciar el contenedor completo.
    """
    user_id = user.get("user_id")
    is_admin = user.get("role") == "admin"

    hosting = hosting_repo.get_hosting_any(hosting_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting not found")
    if not is_admin and str(hosting.get("user_id")) != str(user_id):
        raise HTTPException(status_code=403, detail="Acceso denegado")
    if hosting.get("status") == "deleted":
        raise HTTPException(status_code=409, detail="hosting_deleted")

    filename = file.filename or ""

    # Validar que sea un ZIP
    if not filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos .zip")

    container_name = hosting["container_name"]

    try:
        from app.services.activity_service import log_event as _log
        _log(user_id=user_id, hosting_id=hosting_id,
             event_type="static_zip_upload_started", category="hosting", severity="info",
             title=f"ZIP upload iniciado: {hosting.get('name') or hosting_id}",
             message=filename,
             ip=request.client.host if request.client else None, source="dashboard",
             metadata={"filename": filename})
    except Exception:
        pass

    site_dir = os.path.join("/opt/clients", container_name)
    # Record BEFORE makedirs — bind-mount only if dir already existed
    has_host_mount = os.path.isdir(site_dir)
    os.makedirs(site_dir, exist_ok=True)

    if not os.access(site_dir, os.W_OK):
        raise HTTPException(
            status_code=503,
            detail={
                "ok": False,
                "code": "import_dir_not_writable",
                "message": f"El directorio de uploads no es escribible. Contacta al administrador.",
            },
        )

    tmp_zip = os.path.join(site_dir, "_upload.zip")
    extracted_dir = os.path.join(site_dir, "_extracted")

    try:
        # A. Stream directly to disk — no in-memory accumulation
        total = 0
        with open(tmp_zip, "wb") as fh:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_ZIP_SIZE:
                    _log_static_upload_rejection(
                        request, user_id, hosting_id, filename, total,"zip_too_large"
                    )
                    raise HTTPException(
                        status_code=400,
                        detail=f"Archivo demasiado grande. Máximo permitido: {MAX_ZIP_SIZE // (1024 * 1024)} MB.",
                    )
                fh.write(chunk)

        # B. Validar magic bytes
        with open(tmp_zip, "rb") as fh:
            header = fh.read(4)
        if header != b"PK\x03\x04":
            _log_static_upload_rejection(
                request, user_id, hosting_id, filename, total,"invalid_zip_magic"
            )
            raise HTTPException(status_code=400, detail="El archivo no es un ZIP válido o está corrupto.")

        # C. Extraer a directorio temporal
        if os.path.exists(extracted_dir):
            shutil.rmtree(extracted_dir)
        os.makedirs(extracted_dir, exist_ok=True)

        try:
            with zipfile.ZipFile(tmp_zip, "r") as zf:
                total_size = sum(info.file_size for info in zf.infolist())
                if total_size > MAX_EXTRACTED_SIZE:
                    _log_static_upload_rejection(
                        request, user_id, hosting_id, filename, total,"extracted_size_limit_exceeded"
                    )
                    raise HTTPException(
                        status_code=400,
                        detail=f"El contenido descomprimido excede el límite de {MAX_EXTRACTED_SIZE // (1024 * 1024)} MB.",
                    )
                _safe_extract_zip(zf, Path(extracted_dir))
        except _ZipValidationError as exc:
            _log_static_upload_rejection(
                request, user_id, hosting_id, filename, total,exc.reason
            )
            raise HTTPException(status_code=400, detail=exc.detail)
        except zipfile.BadZipFile:
            _log_static_upload_rejection(
                request, user_id, hosting_id, filename, total,"bad_zip_file"
            )
            raise HTTPException(status_code=400, detail="El archivo no es un ZIP válido o está corrupto.")

        # 3. Detectar si el ZIP tiene carpeta raíz única ignorando __MACOSX
        entries = [e for e in os.listdir(extracted_dir) if e != "__MACOSX"]
        if len(entries) == 1 and os.path.isdir(os.path.join(extracted_dir, entries[0])):
            serve_root = os.path.join(extracted_dir, entries[0])
        else:
            serve_root = extracted_dir

        # 4. Detectar subdirectorio de build si existe (dist/, build/, public/, etc.)
        serve_dir = _find_serve_dir(serve_root)

        # Reject empty archives
        if not any(True for _ in os.scandir(serve_dir)):
            _log_static_upload_rejection(
                request, user_id, hosting_id, filename, total,"zip_empty"
            )
            raise HTTPException(status_code=400, detail="El ZIP no contiene archivos.")

        # Require index.html at the serve root
        if not os.path.isfile(os.path.join(serve_dir, "index.html")):
            _log_static_upload_rejection(
                request, user_id, hosting_id, filename, total,"missing_index_html"
            )
            raise HTTPException(
                status_code=400,
                detail="El ZIP debe contener index.html en la raíz del sitio.",
            )

        files_applied = sum(len(ff) for _, _, ff in os.walk(serve_dir))
        index_html_present = True

        # 5. Estrategia dual según tipo de contenedor:
        #    - Contenedores con bind-mount (GitHub deploy): actualizar archivos en el HOST
        #      ya que /opt/clients/{container}/ es el directorio montado como read-only.
        #    - Contenedores sin mount (create-hosting vacío): usar docker cp.

        deployed_via_host = False

        # F. Atomic swap: stage new content, backup old, move in new, restore on failure
        if has_host_mount:
            _backup_dir = os.path.join(site_dir, "_backup")
            _new_dir = os.path.join(site_dir, "_new")
            try:
                for _d in (_backup_dir, _new_dir):
                    if os.path.exists(_d):
                        shutil.rmtree(_d)
                shutil.copytree(serve_dir, _new_dir)
                os.makedirs(_backup_dir, exist_ok=True)
                for item in os.listdir(site_dir):
                    if item in _SWAP_SKIP:
                        continue
                    shutil.move(os.path.join(site_dir, item), os.path.join(_backup_dir, item))
                for item in os.listdir(_new_dir):
                    shutil.move(os.path.join(_new_dir, item), os.path.join(site_dir, item))
                deployed_via_host = True
                shutil.rmtree(_backup_dir, ignore_errors=True)
                shutil.rmtree(_new_dir, ignore_errors=True)
            except Exception as _swap_exc:
                logger.warning("upload_zip: swap failed, rolling back: %s", _swap_exc)
                try:
                    for item in os.listdir(site_dir):
                        if item in _SWAP_SKIP:
                            continue
                        _p = os.path.join(site_dir, item)
                        if os.path.isdir(_p):
                            shutil.rmtree(_p, ignore_errors=True)
                        else:
                            try:
                                os.remove(_p)
                            except OSError:
                                pass
                    if os.path.exists(_backup_dir):
                        for item in os.listdir(_backup_dir):
                            shutil.move(
                                os.path.join(_backup_dir, item),
                                os.path.join(site_dir, item),
                            )
                except Exception as _rb_exc:
                    logger.error("upload_zip: rollback error: %s", _rb_exc)
                finally:
                    shutil.rmtree(_backup_dir, ignore_errors=True)
                    shutil.rmtree(_new_dir, ignore_errors=True)
                _log_static_upload_rejection(
                    request, user_id, hosting_id, filename, total,"upload_atomic_swap_failed"
                )
                raise HTTPException(
                    status_code=503,
                    detail={
                        "ok": False,
                        "code": "upload_atomic_swap_failed",
                        "message": "No se pudo aplicar el ZIP. El contenido anterior fue restaurado.",
                    },
                )

        # Siempre intentar docker cp (cubre contenedores sin bind-mount)
        cp_code, _, cp_err = await run_docker_command_async(
            ["cp", f"{serve_dir}/.", f"{container_name}:/usr/share/nginx/html/"],
            timeout=30,
        )

        if not deployed_via_host and cp_code != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Error desplegando archivos: {cp_err}",
            )

        # 6. Recargar Nginx
        await run_docker_command_async(
            ["exec", container_name, "nginx", "-s", "reload"],
            timeout=10,
        )

        from app.services.activity_service import log_event as _log
        _log(user_id=user_id, hosting_id=hosting_id,
             event_type="static_zip_upload_completed", category="hosting",
             title=f"Sitio desplegado vía ZIP: {hosting.get('name') or hosting_id}",
             message=f"Archivo: {filename}, tamaño: {total} bytes",
             ip=request.client.host if request.client else None, source="dashboard",
             metadata={"filename": filename, "size_bytes": total})
        return {
            "status": "ok",
            "hosting_id": hosting_id,
            "subdomain": hosting["subdomain"],
            "url": f"https://{hosting['subdomain']}",
            "files_applied": files_applied,
            "index_html": index_html_present,
            "target_dir": site_dir,
        }

    except HTTPException:
        try:
            from app.services.activity_service import log_event as _log
            _log(user_id=user_id, hosting_id=hosting_id,
                 event_type="static_zip_upload_failed", category="hosting", severity="warning",
                 title=f"ZIP rechazado: {hosting.get('name') or hosting_id}",
                 ip=request.client.host if request.client else None, source="dashboard",
                 metadata={"filename": filename})
        except Exception:
            pass
        raise
    except Exception as e:
        try:
            from app.services.activity_service import log_event as _log
            _log(user_id=user_id, hosting_id=hosting_id,
                 event_type="static_zip_upload_failed", category="hosting", severity="warning",
                 title=f"Error desplegando ZIP: {hosting.get('name') or hosting_id}",
                 message=str(e)[:200],
                 ip=request.client.host if request.client else None, source="dashboard",
                 metadata={"filename": filename})
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Limpiar archivos temporales
        if os.path.exists(tmp_zip):
            os.remove(tmp_zip)
        if os.path.exists(extracted_dir):
            shutil.rmtree(extracted_dir, ignore_errors=True)



from app.services.hosting.orchestrator_events_service import get_orchestrator_events

dedicated_orchestrator_events_route = router.get("/orchestrator/events")(get_orchestrator_events)

from app.services.hosting.diagnose_service import diagnose_hosting

router.post("/hosting/{hosting_id}/diagnose")(
    limiter.limit("6/minute")(diagnose_hosting)
)


@router.get("/hosting/{hosting_id}/ai-history")
async def get_ai_diagnosis_history(
    hosting_id: int,
    limit: int = 10,
    user: dict = Depends(verify_token),
):
    """
    Returns the most recent structured AI diagnoses for a hosting.
    Verifies the hosting belongs to the requesting user.
    """
    from app.infra.audit.ai_diagnosis_repository import AIDiagnosisRepository
    from app.infra.audit.hosting_repository import HostingRepository

    user_id = int(user["user_id"])
    hosting = HostingRepository().get_hosting(hosting_id, user_id)
    if not hosting or str(hosting["user_id"]) != str(user_id):
        raise HTTPException(status_code=404, detail="Hosting no encontrado o sin permisos")

    return AIDiagnosisRepository().get_by_hosting(hosting_id, limit=min(limit, 20))


@router.get("/hosting/{hosting_id}/fix")
async def get_fix_proposal(hosting_id: int, user: dict = Depends(verify_token)):
    """
    Return the cached FixProposal for the hosting's current diagnosis fingerprint.
    Rebuilds from the latest diagnosis if nothing is in the cache.
    Returns 204 when no fix is applicable (clean system or no diagnosis yet).
    """
    from app.infra.audit.ai_diagnosis_repository import AIDiagnosisRepository
    from app.services.fix_engine import build_fix_proposal
    from app.services.fix_memory import get_proposal, save_proposal

    user_id = int(user["user_id"])
    hosting = hosting_repo.get_hosting(hosting_id, user_id)
    if not hosting or str(hosting["user_id"]) != str(user_id):
        raise HTTPException(status_code=404, detail="Hosting no encontrado o sin permisos")

    # Fetch the latest diagnosis to get the fingerprint
    diag_repo = AIDiagnosisRepository()
    history = diag_repo.get_by_hosting(hosting_id, limit=1)
    if not history:
        return {"proposed_fix": None}

    latest = history[0]
    # Prefer the real fingerprint stored during diagnosis (exact cache key match).
    # Fall back to a stable surrogate key based on the row id.
    cache_fp = latest.get("fingerprint") or f"diag-{latest['id']}"

    # 1. Cache hit — fix_memory already has the proposal from diagnose_hosting
    cached = get_proposal(hosting_id, cache_fp)
    if cached:
        return {"proposed_fix": cached.model_dump()}

    # 2. Cache miss — rebuild from stored diagnosis fields
    failure_type = latest.get("failure_type") or "unknown"
    # Map diagnosis severity to a rough score estimate for the fix engine threshold.
    # Critical → 30, warning → 60, info → 90.  Only affects nginx_reload selection.
    _sev_score = {"critical": 30, "warning": 60, "info": 90}
    approx_score = _sev_score.get(latest.get("severity"), 60)

    proposal = build_fix_proposal(
        hosting_id=hosting_id,
        container_name=hosting["container_name"],
        fingerprint=cache_fp,
        failure_type=failure_type,
        container_status="running",   # assume running — inspect skipped for latency
        score=approx_score,
    )
    if proposal:
        save_proposal(proposal)
        return {"proposed_fix": proposal.model_dump()}

    return {"proposed_fix": None}


class ApplyFixRequest(BaseModel):
    hosting_id: int
    fingerprint: str
    approved: bool


@router.post("/fix/apply")
@limiter.limit("5/minute")
async def apply_fix(data: ApplyFixRequest, request: Request, user: dict = Depends(verify_token)):
    """
    Execute an approved FixProposal.
    Requires approved=True — this is the human gate that must be satisfied
    before any command runs. Automatically rolls back on failure.
    """
    from app.services.fix_memory import get_proposal, delete_proposal
    from app.services.execution_engine import execute_fix

    if not data.approved:
        raise HTTPException(status_code=400, detail="Fix must be explicitly approved (approved=true).")

    user_id = int(user["user_id"])
    hosting = hosting_repo.get_hosting(data.hosting_id, user_id)
    if not hosting or str(hosting["user_id"]) != str(user_id):
        raise HTTPException(status_code=404, detail="Hosting no encontrado o sin permisos")

    proposal = get_proposal(data.hosting_id, data.fingerprint)
    if not proposal:
        raise HTTPException(status_code=404, detail="Fix proposal no encontrado o expirado. Ejecutá un diagnóstico nuevo.")

    # Safety: verify the proposal targets the hosting the user owns
    if proposal.container_name != hosting["container_name"]:
        raise HTTPException(status_code=400, detail="Fix proposal no corresponde a este hosting.")

    result = await execute_fix(proposal)

    # Invalidate the cache on success so the next diagnosis sees a fresh state
    if result.success:
        delete_proposal(data.hosting_id, data.fingerprint)

    return result.model_dump()


@router.post("/hostings/{hosting_id}/wp-reset-password")
def wp_reset_password(hosting_id: int, user: dict = Depends(verify_token)):
    hosting = hosting_repo.get_hosting(hosting_id, user["user_id"])
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting no encontrado.")
    if hosting["status"] not in ("active", "running"):
        raise HTTPException(status_code=409, detail="El sitio debe estar activo para restablecer la contraseña.")

    new_password = secrets.token_urlsafe(14)
    container = hosting["container_name"]

    result = subprocess.run(
        ["docker", "exec", container,
         "wp", "--allow-root", "user", "update", "admin",
         f"--user_pass={new_password}", "--skip-email"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        logger.error("[wp-reset-pw] %s stderr: %s", container, result.stderr)
        raise HTTPException(status_code=500, detail="No se pudo restablecer la contraseña en WordPress.")

    # Persist new password so the hosting list can show it
    hosting_repo.set_wp_credentials(hosting_id, new_password)

    return {"password": new_password}


@router.get("/{hosting_id}/health/history")
async def get_health_history_legacy(hosting_id: int, user: dict = Depends(verify_token)):
    user_id = int(user["user_id"])
    if not hosting_repo.get_hosting(hosting_id, user_id):
        raise HTTPException(status_code=404, detail="Hosting not found")
    data = _health_repo.get_health_history(hosting_id)
    return [
        {
            "score": row["score"],
            "cpu": row["cpu"],
            "ram": row["ram"],
            "timestamp": row["created_at"]
        }
        for row in data
    ]

