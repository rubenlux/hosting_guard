"""
Docker-based build helpers.

Provides env-flag building, version parsing, image selection,
Traefik label generation, and the tool-presence check.
"""
import shutil
from typing import Optional

from app.services.deploy_diagnostics import DeployError, DEPLOY_RUNTIME_MISSING_TOOL


def _parse_versions(stdout: str) -> tuple[str, str]:
    """Extract node/npm versions from `node --version && npm --version` output."""
    lines = [l.strip() for l in stdout.splitlines() if l.strip()]
    node = next((l for l in lines if l.startswith("v")), "unknown")
    npm  = next((l for l in lines if l and l[0].isdigit()), "unknown")
    return node, npm


def _docker_env_flags(env_vars: dict) -> list:
    flags = []
    for k, v in env_vars.items():
        flags += ["-e", f"{k}={v}"]
    return flags


def _detect_image_for_start(work_dir: str, framework: Optional[str]) -> str:
    import os
    if framework in ("python", "fastapi", "flask", "django"):
        return "python:3.11-slim"
    if framework in ("node", "express", "nextjs", "nuxt"):
        return "node:20-alpine"
    if os.path.exists(f"{work_dir}/requirements.txt"):
        return "python:3.11-slim"
    if os.path.exists(f"{work_dir}/package.json"):
        return "node:20-alpine"
    return "python:3.11-slim"


def _default_install(image: str) -> str:
    if "python" in image:
        return "pip install --no-cache-dir -r requirements.txt"
    return "npm install --prefer-offline"


def _traefik_labels(container_name: str, subdomain: str, port: int) -> list:
    return [
        "-l", "traefik.enable=true",
        "-l", f"traefik.http.routers.{container_name}.rule=Host(`{subdomain}`)",
        "-l", f"traefik.http.routers.{container_name}.entrypoints=websecure",
        "-l", f"traefik.http.routers.{container_name}.tls.certresolver=le",
        "-l", f"traefik.http.routers.{container_name}.middlewares=hg-forwardauth",
        "-l", f"traefik.http.services.{container_name}.loadbalancer.server.port={port}",
    ]


def _check_required_tool(name: str) -> None:
    """Raise DeployError(503) if `name` is not available in PATH."""
    if shutil.which(name) is None:
        raise DeployError(
            code=DEPLOY_RUNTIME_MISSING_TOOL, stage="runtime_precheck",
            detail=(
                "HostingGuard no pudo iniciar el deploy porque falta una herramienta "
                "interna necesaria. El problema no está en tu repositorio."
            ),
            suggested_fix=(
                f"El administrador debe instalar '{name}' en la imagen del servidor."
            ),
            technical_detail=f"Missing executable: {name}",
            evidence={"missing_tool": name},
            status_code=503,
        )
