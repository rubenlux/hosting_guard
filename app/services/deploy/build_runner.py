"""
Docker-based build helpers.

Provides env-flag building, version parsing, image selection,
Traefik label generation, and the tool-presence check.
"""
import re
import shutil
from typing import Optional

# Env var names (case-insensitive suffix match) that must never reach build containers.
# Build containers are ephemeral and untrusted; credentials injected here can be
# exfiltrated by a malicious postinstall script in a compromised dependency.
_BLOCKED_BUILD_ENV_RE = re.compile(
    r"DATABASE_URL$|DB_PASS|DB_PASSWORD|SECRET_KEY|JWT_SECRET|"
    r"NPM_TOKEN|NODE_AUTH_TOKEN|GITHUB_TOKEN|GH_TOKEN|"
    r"SSH_PRIVATE_KEY|SSH_KEY(?:$|_)|PRIVATE_KEY|API_SECRET",
    re.IGNORECASE,
)

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


def _safe_build_env_flags(env_vars: dict) -> list:
    """Like _docker_env_flags but strips secrets unsafe for ephemeral npm build containers."""
    safe = {k: v for k, v in env_vars.items() if not _BLOCKED_BUILD_ENV_RE.search(k)}
    return _docker_env_flags(safe)


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
