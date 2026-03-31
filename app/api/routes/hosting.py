import subprocess
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.api.security import verify_token
from app.infra.audit.hosting_repository import HostingRepository

hosting_repo = HostingRepository()

router = APIRouter()

DOMAIN = "hostingguard.lat"

# 🔥 planes simples
PLANS = {
    "starter": {"cpu": "0.5", "memory": "512m"},
    "growth": {"cpu": "1", "memory": "1g"},
    "pro": {"cpu": "2", "memory": "2g"},
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

        image = "nginx:alpine"

        command = [
            "docker", "run", "-d",
            "--name", container_name,
            "--network", "hosting_guard_hosting_network",
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
    hostings = hosting_repo.get_user_hostings(user_id)

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

@router.get("/orchestrator/events")
async def get_orchestrator_events(user: dict = Depends(verify_token)):
    user_id = user.get("user_id")
    events = hosting_repo.get_orchestrator_events(user_id)
    return events
