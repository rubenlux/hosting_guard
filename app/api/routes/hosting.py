import subprocess
from fastapi import APIRouter
from pydantic import BaseModel
import uuid

router = APIRouter()

DOMAIN = "hostingguard.lat"

# 🔥 planes simples
PLANS = {
    "starter": {"cpu": "0.25", "memory": "256m"},
    "growth": {"cpu": "0.5", "memory": "512m"},
    "pro": {"cpu": "1", "memory": "1g"},
}


class CreateHostingRequest(BaseModel):
    name: str  # nombre del proyecto (ej: "miapp")
    plan: str  # starter | growth | pro


@router.post("/create-hosting")
def create_hosting(data: CreateHostingRequest):
    try:
        project_name = data.name.lower().replace(" ", "-")
        subdomain = f"{project_name}.{DOMAIN}"
        container_name = f"hg_{project_name}_{uuid.uuid4().hex[:6]}"

        plan = PLANS.get(data.plan)
        if not plan:
            return {"error": "plan inválido"}

        image = "nginx:alpine"

        command = [
            "docker", "run", "-d",
            "--name", container_name,
            "--network", "hosting_guard_hosting_network",
            "-l", "traefik.enable=true",
            "-l", f"traefik.http.routers.{project_name}.rule=Host(`{subdomain}`)",
            "-l", f"traefik.http.routers.{project_name}.entrypoints=websecure",
            "-l", f"traefik.http.routers.{project_name}.tls.certresolver=le",
            image
        ]

        result = subprocess.run(command, capture_output=True, text=True)

        return {
            "status": "created",
            "stdout": result.stdout,
            "stderr": result.stderr,
            "url": f"https://{subdomain}",
            "container": container_name
        }

    except Exception as e:
        return {
            "error": "exception",
            "details": str(e)
        }
