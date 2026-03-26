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
    project_name = data.name.lower().replace(" ", "-")
    subdomain = f"{project_name}.{DOMAIN}"
    container_name = f"hg_{project_name}_{uuid.uuid4().hex[:6]}"

    plan = PLANS.get(data.plan)
    if not plan:
        return {"error": "plan inválido"}

    cpu = plan["cpu"]
    memory = plan["memory"]

    # 🔥 contenedor base (simple nginx por ahora)
    image = "nginx:alpine"

    command = [
        "docker", "run", "-d",
        "--name", container_name,
        "--cpus", cpu,
        "--memory", memory,

        "-l", "traefik.enable=true",
        "-l", f"traefik.http.routers.{container_name}.rule=Host(`{subdomain}`)",
        "-l", "traefik.http.routers."+container_name+".entrypoints=websecure",
        "-l", "traefik.http.routers."+container_name+".tls.certresolver=le",
        "-l", "traefik.http.services."+container_name+".loadbalancer.server.port=80",

        image
    ]

    subprocess.run(command)

    return {
        "status": "created",
        "url": f"https://{subdomain}",
        "container": container_name,
        "plan": data.plan
    }
