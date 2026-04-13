import subprocess
import uuid
import os
import re
import asyncio
import shutil
import zipfile
import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from pydantic import BaseModel
from app.api.security import verify_token, require_support_write
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

_user_repo = UserRepository()
hosting_repo = HostingRepository()
_health_repo = HealthRepository()

# --- Constantes de seguridad ---
MAX_ZIP_SIZE        = 50  * 1024 * 1024   # 50 MB en memoria
MAX_EXTRACTED_SIZE  = 200 * 1024 * 1024   # 200 MB descomprimido (anti ZIP-bomb)
ALLOWED_REPO_HOSTS  = {"github.com", "gitlab.com", "bitbucket.org"}
BRANCH_REGEX        = re.compile(r'^[a-zA-Z0-9._/\-]+$')
PROJECT_NAME_REGEX  = re.compile(r'^[a-z0-9][a-z0-9\-]{1,48}[a-z0-9]$')
# Formatos válidos para --since de docker logs: "5m", "2h", "3d", "2024-01-15T10:00:00"
_SINCE_REGEX        = re.compile(r'^\d+[smhd]$|^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$')


def _find_serve_dir(site_dir: str) -> str:
    for subdir in ["public", "dist", "build", "www", "_site", "frontend/dist"]:
        candidate = f"{site_dir}/{subdir}"
        if os.path.exists(f"{candidate}/index.html"):
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
    """Valida que la URL sea HTTPS y pertenezca a un host de confianza."""
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


class CreateHostingRequest(BaseModel):
    name: str
    plan: str


@router.post("/create-hosting")
async def create_hosting(data: CreateHostingRequest, request: Request, user: dict = Depends(verify_token)):
    try:
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

        max_sites = plan.get("max_sites")
        if max_sites is not None:
            user_hostings = hosting_repo.get_user_hostings(user_id)
            if len(user_hostings) >= max_sites:
                raise HTTPException(
                    status_code=403,
                    detail=f"Límite de proyectos alcanzado para el plan {data.plan}. Máximo permitido: {max_sites}."
                )

        image = "nginx:alpine"

        command = [
            "run", "-d",
            "--name",     container_name,
            "--network",  "deploy_hosting_network",
            # FIX #7: aplicar límites de recursos del plan (antes faltaban en este endpoint)
            "--cpus",     plan["cpu"],
            "--memory",   plan["memory"],
            "-l", "traefik.enable=true",
            "-l", f"traefik.http.routers.{container_name}.rule=Host(`{subdomain}`)",
            "-l", f"traefik.http.routers.{container_name}.entrypoints=websecure",
            "-l", f"traefik.http.routers.{container_name}.tls.certresolver=le",
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

        return {
            "status":     "created",
            "hosting_id": hosting_id,
            "user_id":    user_id,
            "url":        f"https://{subdomain}",
            "container":  container_name
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


from app.services.hosting.list_service import list_hostings

router.get("/list-hostings")(list_hostings)



@router.delete("/delete-hosting/{hosting_id}")
async def delete_hosting(hosting_id: int, user: dict = Depends(require_support_write)):
    user_id = user.get("user_id")
    hosting = hosting_repo.get_hosting(hosting_id, user_id)

    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting not found")

    container_name = hosting["container_name"]

    await run_docker_command_async(["rm", "-f", container_name], timeout=15)

    # FIX #2: si es WordPress, eliminar también el contenedor de DB huérfano.
    # Convención de nombres: user_{id}_wp_{name}_{uid}  →  user_{id}_db_{name}_{uid}
    if "_wp_" in container_name:
        db_container = container_name.replace("_wp_", "_db_", 1)
        await run_docker_command_async(["rm", "-f", db_container], timeout=15)

    hosting_repo.delete_hosting(hosting_id, user_id)
    return {"status": "deleted", "hosting_id": hosting_id}

@router.post("/hostings/{hosting_id}/restart")
async def restart_hosting(hosting_id: int, user: dict = Depends(verify_token)):
    user_id = user.get("user_id")
    hosting = hosting_repo.get_hosting(hosting_id, user_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting not found")
    await run_docker_command_async(["restart", hosting["container_name"]], timeout=20)
    return {"status": "restarting"}


@router.post("/hostings/{hosting_id}/stop")
async def stop_hosting(hosting_id: int, user: dict = Depends(verify_token)):
    user_id = user.get("user_id")
    hosting = hosting_repo.get_hosting(hosting_id, user_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting not found")
    await run_docker_command_async(["stop", hosting["container_name"]], timeout=20)
    return {"status": "stopped"}


@router.post("/hostings/{hosting_id}/start")
async def start_hosting(hosting_id: int, user: dict = Depends(verify_token)):
    user_id = user.get("user_id")
    hosting = hosting_repo.get_hosting(hosting_id, user_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting not found")
    await run_docker_command_async(["start", hosting["container_name"]], timeout=20)
    return {"status": "starting"}

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

        plan = PLANS.get(data.plan)
        if not plan:
            raise HTTPException(status_code=400, detail="plan inválido")

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

        max_sites = plan.get("max_sites")
        if max_sites is not None:
            user_hostings = hosting_repo.get_user_hostings(user_id)
            if len(user_hostings) >= max_sites:
                raise HTTPException(
                    status_code=403,
                    detail=f"Límite de proyectos alcanzado para el plan {data.plan}. Máximo permitido: {max_sites}."
                )

        # FIX #9: la contraseña se genera y se pasa a ambos contenedores correctamente
        # (el patrón de nombres garantiza que delete_hosting pueda limpiar db_container)
        db_password = uuid.uuid4().hex[:16]

        # 1. Lanzar MariaDB
        db_cmd = [
            "run", "-d",
            "--name",    db_container,
            "--network", network,
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
            "-l", f"traefik.http.services.{wp_container}.loadbalancer.server.port=80",
            "wordpress:latest"
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
            plan=data.plan,
            ip_address=ip_address
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
    name: str
    plan: str
    repo_url: str
    branch: str = "main"


@router.post("/deploy-from-github")
async def deploy_from_github(data: GitDeployRequest, request: Request, user: dict = Depends(verify_token)):
    try:
        # FIX #4: validar URL antes de usarla en subprocess
        # FIX #5: validar branch para prevenir command injection
        # FIX #7: validar nombre de proyecto
        _validate_project_name(data.name)
        _validate_repo_url(data.repo_url)
        _validate_branch(data.branch)

        user_id        = user.get("user_id")
        project_name   = data.name.lower().replace(" ", "-")
        subdomain      = f"{project_name}.{DOMAIN}"
        uid            = uuid.uuid4().hex[:6]
        container_name = f"user_{user_id}_git_{project_name}_{uid}"
        site_dir       = f"/opt/clients/{container_name}"
        ip_address     = _get_real_ip(request)

        plan = PLANS.get(data.plan)
        if not plan:
            raise HTTPException(status_code=400, detail="Plan inválido")

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

        max_sites = plan.get("max_sites")
        if max_sites is not None:
            user_hostings = hosting_repo.get_user_hostings(user_id)
            if len(user_hostings) >= max_sites:
                raise HTTPException(
                    status_code=403,
                    detail=f"Límite de proyectos alcanzado para el plan {data.plan}. Máximo permitido: {max_sites}."
                )

        loop = asyncio.get_running_loop()

        # 1. Clonar el repo (FIX #1: no bloqueante)
        clone_result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                ["git", "clone", "--branch", data.branch, "--depth", "1", data.repo_url, site_dir],
                capture_output=True, text=True, timeout=60
            )
        )
        if clone_result.returncode != 0:
            raise HTTPException(status_code=400, detail=f"Error clonando repo: {clone_result.stderr}")

        # 2. Detectar tipo de proyecto
        import json as _json
        has_package_json  = False
        package_json_path = f"{site_dir}/package.json"
        if os.path.exists(package_json_path):
            try:
                with open(package_json_path) as f:
                    pkg = _json.load(f)
                scripts = pkg.get("scripts", {})
                deps    = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                has_package_json = "build" in scripts and any(
                    k in deps for k in ["react", "vue", "vite", "next", "nuxt", "svelte"]
                )
            except Exception:
                has_package_json = False

        # 3. Lanzar contenedor según tipo
        if has_package_json:
            image   = "node:20-alpine"
            cmd_str = (
                "npm install && npm run build && "
                "if [ -d dist ]; then npx serve dist -l 80; "
                "elif [ -d build ]; then npx serve build -l 80; "
                "else npx serve . -l 80; fi"
            )
            command = [
                "run", "-d",
                "--name",    container_name,
                "--network", "deploy_hosting_network",
                "--cpus",    plan["cpu"],
                "--memory",  plan["memory"],
                "-v", f"{site_dir}:/app",
                "-w", "/app",
                "-l", "traefik.enable=true",
                "-l", f"traefik.http.routers.{container_name}.rule=Host(`{subdomain}`)",
                "-l", f"traefik.http.routers.{container_name}.entrypoints=websecure",
                "-l", f"traefik.http.routers.{container_name}.tls.certresolver=le",
                "-l", f"traefik.http.services.{container_name}.loadbalancer.server.port=80",
                image, "sh", "-c", cmd_str
            ]
        else:
            command = [
                "run", "-d",
                "--name",    container_name,
                "--network", "deploy_hosting_network",
                "--cpus",    plan["cpu"],
                "--memory",  plan["memory"],
                "-v", f"{_find_serve_dir(site_dir)}:/usr/share/nginx/html:ro",
                "-l", "traefik.enable=true",
                "-l", f"traefik.http.routers.{container_name}.rule=Host(`{subdomain}`)",
                "-l", f"traefik.http.routers.{container_name}.entrypoints=websecure",
                "-l", f"traefik.http.routers.{container_name}.tls.certresolver=le",
                "-l", f"traefik.http.services.{container_name}.loadbalancer.server.port=80",
                "nginx:alpine"
            ]

        code, _, stderr = await run_docker_command_async(command, timeout=60)
        if code != 0:
            await loop.run_in_executor(None, lambda: subprocess.run(["rm", "-rf", site_dir]))
            raise HTTPException(status_code=500, detail=f"Docker error: {stderr}")

        hosting_id = hosting_repo.create_hosting(
            user_id=user_id,
            name=data.name,
            subdomain=subdomain,
            container_name=container_name,
            plan=data.plan,
            ip_address=ip_address
        )

        return {
            "status":     "deployed",
            "type":       "github",
            "hosting_id": hosting_id,
            "url":        f"https://{subdomain}",
            "repo":       data.repo_url,
            "branch":     data.branch,
            "note":       "Sitio desplegado desde GitHub. Listo en 30 segundos."
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/hostings/{hosting_id}/redeploy")
async def redeploy_from_github(hosting_id: int, user: dict = Depends(verify_token)):
    """Hace git pull y reinicia el contenedor."""
    user_id = user.get("user_id")
    hosting = hosting_repo.get_hosting(hosting_id, user_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting not found")

    container_name = hosting["container_name"]
    site_dir       = f"/opt/clients/{container_name}"

    if not os.path.exists(site_dir):
        raise HTTPException(status_code=400, detail="No es un deploy de GitHub")

    # FIX #8: verificar que el directorio sea un repo git válido antes de hacer pull
    if not os.path.exists(os.path.join(site_dir, ".git")):
        raise HTTPException(
            status_code=400,
            detail="El directorio no contiene un repositorio Git válido."
        )

    loop = asyncio.get_running_loop()
    # FIX #1: no bloqueante
    pull = await loop.run_in_executor(
        None,
        lambda: subprocess.run(
            ["git", "-C", site_dir, "pull"],
            capture_output=True, text=True, timeout=30
        )
    )
    await run_docker_command_async(["restart", container_name], timeout=20)

    return {
        "status":     "redeployed",
        "git_output": pull.stdout,
        "container":  container_name
    }

@router.post("/hostings/{hosting_id}/upload-zip")
async def upload_zip(
    hosting_id: int,
    file: UploadFile = File(...),
    user: dict = Depends(verify_token)
):
    """
    Opción C — ZIP upload.
    El cliente sube un .zip con su sitio; el sistema lo extrae y despliega
    en el contenedor Nginx del hosting sin reiniciar el contenedor completo.
    """
    user_id = user.get("user_id")
    hosting = hosting_repo.get_hosting(hosting_id, user_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting not found")

    # Validar que sea un ZIP
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos .zip")

    container_name = hosting["container_name"]

    # Directorio de trabajo en el host
    site_dir = f"/opt/clients/{container_name}"
    os.makedirs(site_dir, exist_ok=True)

    tmp_zip = os.path.join(site_dir, "_upload.zip")
    extracted_dir = os.path.join(site_dir, "_extracted")

    try:
        # FIX #6: leer en chunks para evitar agotamiento de RAM con archivos gigantes
        contents = b""
        chunk_size = 1024 * 1024  # 1 MB por chunk
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            contents += chunk
            if len(contents) > MAX_ZIP_SIZE:
                raise HTTPException(
                    status_code=400,
                    detail=f"Archivo demasiado grande. Máximo permitido: {MAX_ZIP_SIZE // (1024 * 1024)} MB."
                )

        with open(tmp_zip, "wb") as f:
            f.write(contents)

        # 2. Extraer a directorio temporal
        if os.path.exists(extracted_dir):
            shutil.rmtree(extracted_dir)
        os.makedirs(extracted_dir, exist_ok=True)

        # FIX #6: protección contra ZIP bomb — verificar tamaño total antes de extraer
        with zipfile.ZipFile(tmp_zip, "r") as zf:
            total_size = sum(info.file_size for info in zf.infolist())
            if total_size > MAX_EXTRACTED_SIZE:
                raise HTTPException(
                    status_code=400,
                    detail=f"El contenido descomprimido excede el límite de {MAX_EXTRACTED_SIZE // (1024 * 1024)} MB."
                )
            zf.extractall(extracted_dir)

        # 3. Detectar si el ZIP tiene carpeta raíz única ignorando __MACOSX
        entries = [e for e in os.listdir(extracted_dir) if e != "__MACOSX"]
        if len(entries) == 1 and os.path.isdir(os.path.join(extracted_dir, entries[0])):
            serve_root = os.path.join(extracted_dir, entries[0])
        else:
            serve_root = extracted_dir

        # 4. Detectar subdirectorio de build si existe (dist/, build/, public/, etc.)
        serve_dir = _find_serve_dir(serve_root)

        # 5. Estrategia dual según tipo de contenedor:
        #    - Contenedores con bind-mount (GitHub deploy): actualizar archivos en el HOST
        #      ya que /opt/clients/{container}/ es el directorio montado como read-only.
        #    - Contenedores sin mount (create-hosting vacío): usar docker cp.

        deployed_via_host = False

        # 5a. Si existe el directorio del cliente en el host, sincronizar directamente
        if os.path.isdir(site_dir):
            # Limpiar archivos existentes (excepto archivos especiales del sistema)
            for item in os.listdir(site_dir):
                item_path = os.path.join(site_dir, item)
                # No borrar archivos temporales propios ni .git
                if item in ("_upload.zip", "_extracted", ".git"):
                    continue
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                else:
                    os.remove(item_path)

            # Copiar archivos nuevos al directorio del host
            for item in os.listdir(serve_dir):
                src = os.path.join(serve_dir, item)
                dst = os.path.join(site_dir, item)
                if os.path.isdir(src):
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dst)

            deployed_via_host = True

                # 5b. Intentar docker cp también (funciona para contenedores sin volume mount)
        cp_code, _, cp_err = await run_docker_command_async(
            ["cp", f"{serve_dir}/.", f"{container_name}:/usr/share/nginx/html/"],
            timeout=30,
        )

        if not deployed_via_host and cp_code != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Error desplegando archivos: {cp_err}"
            )

        # 6. Recargar Nginx
        await run_docker_command_async(
            ["exec", container_name, "nginx", "-s", "reload"],
            timeout=10,
        )

        return {
            "status": "deployed",
            "hosting_id": hosting_id,
            "url": f"https://{hosting['subdomain']}",
            "message": "Sitio desplegado correctamente. Activo en segundos."
        }

    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="El archivo ZIP está corrupto o es inválido")
    except HTTPException:
        raise
    except Exception as e:
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

router.post("/hosting/{hosting_id}/diagnose")(diagnose_hosting)


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
    # Fingerprint is not stored in get_by_hosting — rebuild it from stored fields.
    # We use the diagnosis id as a stable surrogate key for the cache lookup.
    cache_key_fp = f"diag-{latest['id']}"

    # 1. Cache hit
    cached = get_proposal(hosting_id, cache_key_fp)
    if cached:
        return {"proposed_fix": cached.model_dump()}

    # 2. Rebuild from stored diagnosis fields
    failure_type = latest.get("failure_type") or "unknown"
    proposal = build_fix_proposal(
        hosting_id=hosting_id,
        container_name=hosting["container_name"],
        fingerprint=cache_key_fp,
        failure_type=failure_type,
        container_status="running",   # assume running — we can't inspect now without docker call
        score=80,                      # conservative default when score isn't stored in ai_diagnosis
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
async def apply_fix(data: ApplyFixRequest, user: dict = Depends(verify_token)):
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


@router.get("/{hosting_id}/health/history")
async def get_health_history_legacy(hosting_id: int, user: dict = Depends(verify_token)):
    """Endpoint solicitado por la guía de implementación."""
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

