import subprocess
import uuid
import os
import shutil
import tempfile
import zipfile
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from app.api.security import verify_token
from app.infra.audit.hosting_repository import HostingRepository

hosting_repo = HostingRepository()


def _find_serve_dir(site_dir: str) -> str:
    import os
    for subdir in ["public", "dist", "build", "www", "_site", "frontend/dist"]:
        candidate = f"{site_dir}/{subdir}"
        if os.path.exists(f"{candidate}/index.html"):
            return candidate
    return site_dir


router = APIRouter()

DOMAIN = "hostingguard.lat"

# 🔥 planes simples
PLANS = {
    "free": {"cpu": "0.25", "memory": "256m", "max_sites": 1, "days": 14},
    "personal": {"cpu": "0.5", "memory": "512m", "max_sites": 1, "days": None},
    "negocio": {"cpu": "1", "memory": "1g", "max_sites": 3, "days": None},
    "agencia": {"cpu": "2", "memory": "2g", "max_sites": None, "days": None},
}


class CreateHostingRequest(BaseModel):
    name: str  # nombre del proyecto (ej: "miapp")
    plan: str  # starter | growth | pro


@router.post("/create-hosting")
async def create_hosting(data: CreateHostingRequest, user: dict = Depends(verify_token)):
    try:
        user_id = user.get("user_id")
        project_name = data.name.lower().replace(" ", "-")
        subdomain = f"{project_name}.{DOMAIN}"
        
        # 🔥 Multi-tenant: nombre único por usuario
        container_name = f"user_{user_id}_{project_name}_{uuid.uuid4().hex[:6]}"

        plan = PLANS.get(data.plan)
        if not plan:
            raise HTTPException(status_code=400, detail="plan inválido")

        max_sites = plan.get("max_sites")
        if max_sites is not None:
            user_hostings = hosting_repo.get_user_hostings(user_id)
            if len(user_hostings) >= max_sites:
                raise HTTPException(status_code=403, detail=f"Límite de proyectos alcanzado para el plan {data.plan}. Máximo permitido: {max_sites}.")

        image = "nginx:alpine"

        command = [
            "docker", "run", "-d",
            "--name", container_name,
            "--network", "deploy_hosting_network",
            "-l", "traefik.enable=true",
            "-l", f"traefik.http.routers.{container_name}.rule=Host(`{subdomain}`)",
            "-l", f"traefik.http.routers.{container_name}.entrypoints=websecure",
            "-l", f"traefik.http.routers.{container_name}.tls.certresolver=le",
            "-l", f"traefik.http.services.{container_name}.loadbalancer.server.port=80",
            image
        ]

        result = subprocess.run(command, capture_output=True, text=True)

        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Docker error: {result.stderr}")

        # 🔥 Persistir en DB
        hosting_id = hosting_repo.create_hosting(
            user_id=user_id,
            name=data.name,
            subdomain=subdomain,
            container_name=container_name,
            plan=data.plan
        )

        return {
            "status": "created",
            "hosting_id": hosting_id,
            "user_id": user_id,
            "url": f"https://{subdomain}",
            "container": container_name
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list-hostings")
async def list_hostings(user: dict = Depends(verify_token)):
    user_id = user.get("user_id")
    hostings = hosting_repo.get_all_user_hostings_by_user(user_id)

    # Convertir sqlite3.Row a diccionarios si no lo son
    hostings_list = [dict(h) for h in hostings]

    # Mapeo de estados Docker -> UX
    status_map = {
        "running": "active",
        "exited": "stopped",
        "restarting": "starting",
        "paused": "paused",
        "created": "starting",
        "removing": "stopped",
        "dead": "error"
    }

    for h in hostings_list:
        try:
            # Sincronización real con Docker
            res = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Status}}", h["container_name"]],
                capture_output=True,
                text=True,
                timeout=2
            )

            if res.returncode == 0:
                docker_status = res.stdout.strip()
                h["status"] = status_map.get(docker_status, "unknown")
            else:
                h["status"] = "not_found"

        except Exception:
            h["status"] = "error"

    return hostings_list

@router.delete("/delete-hosting/{hosting_id}")
async def delete_hosting(hosting_id: int, user: dict = Depends(verify_token)):
    user_id = user.get("user_id")
    hosting = hosting_repo.get_hosting(hosting_id, user_id)
    
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting not found")

    # Intentar detener y borrar el contenedor
    try:
        container_name = hosting["container_name"]
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
    except Exception as e:
        print(f"Error deleting container: {e}")

    hosting_repo.delete_hosting(hosting_id, user_id)
    return {"status": "deleted", "hosting_id": hosting_id}

@router.post("/hostings/{hosting_id}/restart")
async def restart_hosting(hosting_id: int, user: dict = Depends(verify_token)):
    user_id = user.get("user_id")
    hosting = hosting_repo.get_hosting(hosting_id, user_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting not found")

    subprocess.run(["docker", "restart", hosting["container_name"]], capture_output=True)
    return {"status": "restarting"}

@router.post("/hostings/{hosting_id}/stop")
async def stop_hosting(hosting_id: int, user: dict = Depends(verify_token)):
    user_id = user.get("user_id")
    hosting = hosting_repo.get_hosting(hosting_id, user_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting not found")

    subprocess.run(["docker", "stop", hosting["container_name"]], capture_output=True)
    return {"status": "stopped"}

@router.post("/hostings/{hosting_id}/start")
async def start_hosting(hosting_id: int, user: dict = Depends(verify_token)):
    user_id = user.get("user_id")
    hosting = hosting_repo.get_hosting(hosting_id, user_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting not found")

    subprocess.run(["docker", "start", hosting["container_name"]], capture_output=True)
    return {"status": "starting"}

@router.get("/hostings/{hosting_id}/logs")
async def get_hosting_logs(hosting_id: int, since: Optional[str] = None, user: dict = Depends(verify_token)):
    user_id = user.get("user_id")
    hosting = hosting_repo.get_hosting(hosting_id, user_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting not found")

    command = ["docker", "logs"]
    if since:
        # Aseguramos que since sea un string válido para docker
        command.extend(["--since", since])
    else:
        command.extend(["--tail", "50"])
    
    command.append(hosting["container_name"])

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=3
        )
        logs = result.stdout if result.stdout else result.stderr
        
        # Devolvemos también el timestamp actual para el próximo 'since'
        return {
            "logs": logs if logs else "",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        return {"logs": f"Error retrieving logs: {str(e)}"}

@router.get("/hostings/{hosting_id}/metrics")
async def get_hosting_metrics(hosting_id: int, user: dict = Depends(verify_token)):
    user_id = user.get("user_id")
    hosting = hosting_repo.get_hosting(hosting_id, user_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting not found")

    try:
        result = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{.CPUPerc}}|{{.MemUsage}}", hosting["container_name"]],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            parts = result.stdout.strip().split("|")
            if len(parts) >= 2:
                return {
                    "cpu": parts[0],
                    "memory": parts[1]
                }
        
        return {"cpu": "0%", "memory": "0MiB / 0MiB"}
    except Exception as e:
        return {"error": str(e)}

@router.post("/create-wordpress")
async def create_wordpress(data: CreateHostingRequest, user: dict = Depends(verify_token)):
    try:
        user_id = user.get("user_id")
        project_name = data.name.lower().replace(" ", "-")
        subdomain = f"{project_name}.{DOMAIN}"
        uid = uuid.uuid4().hex[:6]
        
        db_container = f"user_{user_id}_db_{project_name}_{uid}"
        wp_container = f"user_{user_id}_wp_{project_name}_{uid}"
        network = "deploy_hosting_network"
        
        plan = PLANS.get(data.plan)
        if not plan:
            raise HTTPException(status_code=400, detail="plan inválido")

        max_sites = plan.get("max_sites")
        if max_sites is not None:
            user_hostings = hosting_repo.get_user_hostings(user_id)
            if len(user_hostings) >= max_sites:
                raise HTTPException(status_code=403, detail=f"Límite de proyectos alcanzado para el plan {data.plan}. Máximo permitido: {max_sites}.")

        db_password = uuid.uuid4().hex[:16]

        # 1. Lanzar MySQL
        db_cmd = [
            "docker", "run", "-d",
            "--name", db_container,
            "--network", network,
            "-e", "MYSQL_ROOT_PASSWORD=" + db_password,
            "-e", "MYSQL_DATABASE=wordpress",
            "-e", "MYSQL_USER=wpuser",
            "-e", "MYSQL_PASSWORD=" + db_password,
            "--cpus", plan["cpu"],
            "--memory", plan["memory"],
            "mariadb:10.11"
        ]
        db_result = subprocess.run(db_cmd, capture_output=True, text=True)
        if db_result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"MySQL error: {db_result.stderr}")

        # 2. Lanzar WordPress
        wp_cmd = [
            "docker", "run", "-d",
            "--name", wp_container,
            "--network", network,
            "-e", "WORDPRESS_DB_HOST=" + db_container,
            "-e", "WORDPRESS_DB_USER=wpuser",
            "-e", "WORDPRESS_DB_PASSWORD=" + db_password,
            "-e", "WORDPRESS_DB_NAME=wordpress",
            "--cpus", plan["cpu"],
            "--memory", plan["memory"],
            "-l", "traefik.enable=true",
            "-l", f"traefik.http.routers.{wp_container}.rule=Host(`{subdomain}`)",
            "-l", f"traefik.http.routers.{wp_container}.entrypoints=websecure",
            "-l", f"traefik.http.routers.{wp_container}.tls.certresolver=le",
            "-l", f"traefik.http.services.{wp_container}.loadbalancer.server.port=80",
            "wordpress:latest"
        ]
        wp_result = subprocess.run(wp_cmd, capture_output=True, text=True)
        if wp_result.returncode != 0:
            subprocess.run(["docker", "rm", "-f", db_container], capture_output=True)
            raise HTTPException(status_code=500, detail=f"WordPress error: {wp_result.stderr}")

        # 3. Persistir en DB
        hosting_id = hosting_repo.create_hosting(
            user_id=user_id,
            name=data.name,
            subdomain=subdomain,
            container_name=wp_container,
            plan=data.plan
        )

        return {
            "status": "created",
            "type": "wordpress",
            "hosting_id": hosting_id,
            "url": f"https://{subdomain}",
            "container": wp_container,
            "db_container": db_container,
            "note": "WordPress estará listo en 30-60 segundos"
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
async def deploy_from_github(data: GitDeployRequest, user: dict = Depends(verify_token)):
    try:
        user_id = user.get("user_id")
        project_name = data.name.lower().replace(" ", "-")
        subdomain = f"{project_name}.{DOMAIN}"
        uid = uuid.uuid4().hex[:6]
        container_name = f"user_{user_id}_git_{project_name}_{uid}"
        site_dir = f"/opt/clients/{container_name}"

        plan = PLANS.get(data.plan)
        if not plan:
            raise HTTPException(status_code=400, detail="Plan inválido")

        max_sites = plan.get("max_sites")
        if max_sites is not None:
            user_hostings = hosting_repo.get_user_hostings(user_id)
            if len(user_hostings) >= max_sites:
                raise HTTPException(status_code=403, detail=f"Límite de proyectos alcanzado para el plan {data.plan}. Máximo permitido: {max_sites}.")

        # 1. Clonar el repo en el host
        clone_result = subprocess.run(
            ["git", "clone", "--branch", data.branch, "--depth", "1", data.repo_url, site_dir],
            capture_output=True, text=True, timeout=60
        )
        if clone_result.returncode != 0:
            raise HTTPException(status_code=400, detail=f"Error clonando repo: {clone_result.stderr}")

        # 2. Detectar tipo de proyecto
        import os
        import json
        has_package_json = False
        package_json_path = f"{site_dir}/package.json"
        if os.path.exists(package_json_path):
            try:
                with open(package_json_path) as f:
                    pkg = json.load(f)
                # Solo usar Node si tiene script de build Y es React/Vue/Vite
                scripts = pkg.get("scripts", {})
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                is_node_app = "build" in scripts and any(
                    k in deps for k in ["react", "vue", "vite", "next", "nuxt", "svelte"]
                )
                has_package_json = is_node_app
            except Exception:
                has_package_json = False

        # 3. Lanzar contenedor según tipo
        if has_package_json:
            # Proyecto Node/React — build y servir
            image = "node:20-alpine"
            # Detectar directorio de salida: Vite usa dist/, CRA usa build/
            cmd_str = (
                "npm install && npm run build && "
                "if [ -d dist ]; then npx serve dist -l 80; "
                "elif [ -d build ]; then npx serve build -l 80; "
                "else npx serve . -l 80; fi"
            )
            command = [
                "docker", "run", "-d",
                "--name", container_name,
                "--network", "deploy_hosting_network",
                "--cpus", plan["cpu"],
                "--memory", plan["memory"],
                "-v", f"{site_dir}:/app",
                "-w", "/app",
                "-l", "traefik.enable=true",
                "-l", f"traefik.http.routers.{container_name}.rule=Host(`{subdomain}`)",
                "-l", f"traefik.http.routers.{container_name}.entrypoints=websecure",
                "-l", f"traefik.http.routers.{container_name}.tls.certresolver=le",
                "-l", f"traefik.http.services.{container_name}.loadbalancer.server.port=80",
                image,
                "sh", "-c", cmd_str
            ]
        else:
            # HTML/PHP estático — servir con Nginx
            command = [
                "docker", "run", "-d",
                "--name", container_name,
                "--network", "deploy_hosting_network",
                "--cpus", plan["cpu"],
                "--memory", plan["memory"],
                "-v", f"{_find_serve_dir(site_dir)}:/usr/share/nginx/html:ro",
                "-l", "traefik.enable=true",
                "-l", f"traefik.http.routers.{container_name}.rule=Host(`{subdomain}`)",
                "-l", f"traefik.http.routers.{container_name}.entrypoints=websecure",
                "-l", f"traefik.http.routers.{container_name}.tls.certresolver=le",
                "-l", f"traefik.http.services.{container_name}.loadbalancer.server.port=80",
                "nginx:alpine"
            ]

        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            subprocess.run(["rm", "-rf", site_dir])
            raise HTTPException(status_code=500, detail=f"Docker error: {result.stderr}")

        # 4. Guardar en DB con repo_url
        hosting_id = hosting_repo.create_hosting(
            user_id=user_id,
            name=data.name,
            subdomain=subdomain,
            container_name=container_name,
            plan=data.plan
        )

        return {
            "status": "deployed",
            "type": "github",
            "hosting_id": hosting_id,
            "url": f"https://{subdomain}",
            "repo": data.repo_url,
            "branch": data.branch,
            "note": "Sitio desplegado desde GitHub. Listo en 30 segundos."
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/hostings/{hosting_id}/redeploy")
async def redeploy_from_github(hosting_id: int, user: dict = Depends(verify_token)):
    """Hace git pull y reinicia el contenedor"""
    user_id = user.get("user_id")
    hosting = hosting_repo.get_hosting(hosting_id, user_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting not found")

    container_name = hosting["container_name"]
    site_dir = f"/opt/clients/{container_name}"

    if not os.path.exists(site_dir):
        raise HTTPException(status_code=400, detail="No es un deploy de GitHub")

    pull = subprocess.run(
        ["git", "-C", site_dir, "pull"],
        capture_output=True, text=True, timeout=30
    )

    subprocess.run(["docker", "restart", container_name], capture_output=True)

    return {
        "status": "redeployed",
        "git_output": pull.stdout,
        "container": container_name
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
        # 1. Guardar el ZIP en disco
        contents = await file.read()
        with open(tmp_zip, "wb") as f:
            f.write(contents)

        # 2. Extraer a directorio temporal
        if os.path.exists(extracted_dir):
            shutil.rmtree(extracted_dir)
        os.makedirs(extracted_dir, exist_ok=True)

        with zipfile.ZipFile(tmp_zip, "r") as zf:
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
        cp_result = subprocess.run(
            ["docker", "cp", f"{serve_dir}/.", f"{container_name}:/usr/share/nginx/html/"],
            capture_output=True, text=True, timeout=30
        )

        # Si ambos métodos fallaron, reportar error
        if not deployed_via_host and cp_result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Error desplegando archivos: {cp_result.stderr}"
            )

        # 6. Recargar Nginx
        subprocess.run(
            ["docker", "exec", container_name, "nginx", "-s", "reload"],
            capture_output=True, timeout=10
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



@router.get("/orchestrator/events")
async def get_orchestrator_events(user: dict = Depends(verify_token)):
    user_id = user.get("user_id")
    events = hosting_repo.get_orchestrator_events(user_id)
    return events
