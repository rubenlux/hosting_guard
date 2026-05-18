"""
GitHub deploy orchestration service.

run_github_deploy() encapsulates the full deploy pipeline:
  clone → detect project → npm install → npm build → serve → health check → record

The route handler is responsible for input validation, plan enforcement, and
computing subdomain/container_name before calling this function.
"""
import asyncio
import logging
import os
import subprocess
import tempfile
import uuid
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from fastapi import HTTPException

from app.infra.audit.hosting_repository import HostingRepository
from app.infra.docker_client import run_docker_command_async, TENANT_NETWORK
from app.services.build_diagnostics import (
    classify_npm_failure,
    extract_npm_log_path,
    extract_suspected_package,
    read_npm_log,
)
from app.services.deploy_diagnostics import (
    CONTAINER_START_FAILED,
    GITHUB_BRANCH_NOT_FOUND,
    GITHUB_CLONE_FAILED,
    GITHUB_CLONE_TIMEOUT,
    GITHUB_PRIVATE_REPO_UNAUTHORIZED,
    GITHUB_REPO_NOT_FOUND,
    INDEX_HTML_NOT_FOUND,
    INVALID_REPO_URL,
    MULTIPLE_OUTPUT_DIRECTORIES,
    MULTIPLE_PROJECT_ROOTS,
    PACKAGE_JSON_NOT_FOUND,
    SITE_RETURNS_403,
    SITE_RETURNS_404,
    SITE_RETURNS_502,
    SITE_RETURNS_503,
    SSL_PROVISIONING_TIMEOUT,
    UNKNOWN_DEPLOY_ERROR,
    UNSAFE_PUBLISH_ROOT,
    DeployError,
    record_deploy_event,
)
from app.services.deploy.site_health import check_site_once, wait_for_site_online
from app.services.deploy.build_runner import (
    _check_required_tool,
    _default_install,
    _detect_image_for_start,
    _docker_env_flags,
    _parse_versions,
    _safe_build_env_flags,
    _traefik_labels,
)
from app.services.deploy.project_detector import (
    _WEB_BUILDABLE_DEPS,
    _detect_framework,
    _detect_out_dir,
    _find_buildable_roots,
    _find_serve_dir,
    _read_pkg,
)
from app.services.deploy.dependency_preflight import detect_package_manager, run_dependency_preflight

logger = logging.getLogger(__name__)

_hosting_repo = HostingRepository()

_HC_ERRORS = {
    403: (SITE_RETURNS_403, "El directorio publicado no contiene index.html o nginx bloqueó el acceso. Verificá que se publique el build output, no el repositorio fuente."),
    404: (SITE_RETURNS_404, "El servidor respondió 404. Verificá que el build output contiene index.html."),
    502: (SITE_RETURNS_502, "El contenedor inició pero la app no está escuchando en el puerto esperado."),
    503: (SITE_RETURNS_503, "El contenedor inició pero la app no está disponible."),
}


async def run_github_deploy(
    *,
    data,
    user_id: int,
    ip_address: Optional[str],
    project_name: str,
    subdomain: str,
    container_name: str,
    plan: dict,
) -> dict:
    """
    Full GitHub deploy pipeline. Raises DeployError or HTTPException on failure.
    Records deploy events before re-raising so the route handler only needs to
    build the HTTP response.
    """
    loop = asyncio.get_running_loop()

    site_dir = f"/opt/clients/{container_name}"
    deploy_log: dict = {"started_at": datetime.now().isoformat(), "stages": {}}

    _site_created      = False
    _container_created = False
    _hosting_id: Optional[int] = None
    _detected: dict = {}

    async def _do_cleanup() -> dict:
        cs: dict = {"hosting_row": "not_created", "container": "not_created", "client_dir": "not_removed"}
        if _container_created and container_name:
            r = await loop.run_in_executor(None, lambda: subprocess.run(
                ["docker", "rm", "-f", container_name], capture_output=True
            ))
            cs["container"] = "removed" if r.returncode == 0 else "failed"
        if _site_created and site_dir:
            r = await loop.run_in_executor(None, lambda: subprocess.run(
                ["rm", "-rf", site_dir], capture_output=True
            ))
            cs["client_dir"] = "removed" if r.returncode == 0 else "failed"
        if _hosting_id:
            try:
                _hosting_repo.delete_hosting(_hosting_id)
                cs["hosting_row"] = "deleted"
            except Exception:
                cs["hosting_row"] = "failed"
        return cs

    try:
        # ── Precheck: runtime tools + URL ────────────────────────────────────
        _check_required_tool("git")

        _parsed_url = urlparse(data.repo_url)
        _url_parts  = [p for p in _parsed_url.path.split("/") if p]
        if _parsed_url.scheme != "https" or not _parsed_url.hostname or len(_url_parts) < 2:
            raise DeployError(
                code=INVALID_REPO_URL, stage="validation",
                detail="La URL del repositorio no es válida.",
                suggested_fix="Usá una URL de GitHub válida, por ejemplo https://github.com/usuario/repo.git",
                evidence={"repo_url": data.repo_url[:200]},
            )

        # ── Stage 1: Clone ───────────────────────────────────────────────────
        try:
            clone_result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ["git", "clone", "--branch", data.branch, "--depth", "1", data.repo_url, site_dir],
                    capture_output=True, text=True, timeout=60
                )
            )
        except subprocess.TimeoutExpired:
            _site_created = os.path.exists(site_dir)
            raise DeployError(
                code=GITHUB_CLONE_TIMEOUT, stage="clone",
                detail="El repositorio tardó demasiado en clonarse.",
                suggested_fix="Reintentá o verificá el tamaño/disponibilidad del repositorio.",
                evidence={"timeout_seconds": 60},
            )
        _site_created = True
        deploy_log["stages"]["clone"] = {
            "ok": clone_result.returncode == 0,
            "stdout": clone_result.stdout[-2000:],
            "stderr": clone_result.stderr[-2000:],
        }
        if clone_result.returncode != 0:
            _err = clone_result.stderr.lower()
            if any(m in _err for m in (
                "invalid username or password",
                "authentication failed",
                "could not read username",
                "permission denied (publickey)",
            )):
                raise DeployError(
                    code=GITHUB_PRIVATE_REPO_UNAUTHORIZED, stage="clone",
                    detail="No tenemos permisos para clonar este repositorio.",
                    suggested_fix="Hacé público el repositorio o conectá permisos de GitHub.",
                    technical_detail=clone_result.stderr[-400:],
                )
            if "repository not found" in _err or ("not found" in _err and "repository" in _err):
                raise DeployError(
                    code=GITHUB_REPO_NOT_FOUND, stage="clone",
                    detail="No encontramos el repositorio. Verificá que la URL sea correcta y que el repo sea público.",
                    suggested_fix="Comprobá la URL del repositorio y que sea accesible públicamente.",
                    technical_detail=clone_result.stderr[-400:],
                )
            if "remote branch" in _err or "pathspec" in _err or "couldn't find remote ref" in _err:
                raise DeployError(
                    code=GITHUB_BRANCH_NOT_FOUND, stage="clone",
                    detail=f"No encontramos la rama '{data.branch}' en el repositorio.",
                    suggested_fix="Verificá el nombre de la rama. Las ramas más comunes son 'main' y 'master'.",
                    technical_detail=clone_result.stderr[-400:],
                )
            raise DeployError(
                code=GITHUB_CLONE_FAILED, stage="clone",
                detail="No pudimos clonar el repositorio.",
                suggested_fix="Verificá que la URL sea correcta, que el repo exista y que sea público.",
                technical_detail=clone_result.stderr[-400:],
            )

        work_dir = os.path.join(site_dir, data.root_directory) if data.root_directory else site_dir

        _real_work = os.path.realpath(work_dir)
        _real_site = os.path.realpath(site_dir)
        if not (_real_work == _real_site or _real_work.startswith(_real_site + os.sep)):
            await loop.run_in_executor(None, lambda: subprocess.run(["rm", "-rf", site_dir]))
            raise HTTPException(status_code=400, detail="root_directory no puede salir del repositorio")

        if not os.path.isdir(work_dir):
            await loop.run_in_executor(None, lambda: subprocess.run(["rm", "-rf", site_dir]))
            raise HTTPException(status_code=400,
                detail=f"root_directory '{data.root_directory}' no existe en el repo.")

        # ── Stage 2: Container launch (3 strategies) ─────────────────────────
        has_package_json  = False
        _resolved_out_dir = data.output_directory

        if data.dockerfile_path or data.framework == "dockerfile":
            # Strategy A: build & run from Dockerfile
            df_path = data.dockerfile_path or "Dockerfile"

            _df_full = os.path.realpath(os.path.join(work_dir, df_path))
            if not (_df_full == _real_work or _df_full.startswith(_real_work + os.sep)):
                await loop.run_in_executor(None, lambda: subprocess.run(["rm", "-rf", site_dir]))
                raise HTTPException(status_code=400, detail="dockerfile_path no puede salir de root_directory")

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
                "stdout": build_result.stdout[-3000:],
                "stderr": build_result.stderr[-3000:],
            }
            if build_result.returncode != 0:
                await loop.run_in_executor(None, lambda: subprocess.run(["rm", "-rf", site_dir]))
                raise HTTPException(status_code=500, detail=f"Docker build error: {build_result.stderr[-500:]}")
            command = [
                "run", "-d",
                "--name",    container_name,
                "--network", TENANT_NETWORK,
                "--restart", "unless-stopped",
                "--cpus",    plan["cpu"],
                "--memory",  plan["memory"],
                *_docker_env_flags(data.env_vars),
                *_traefik_labels(container_name, subdomain, data.port),
                image_tag,
            ]

        elif data.start_command:
            # Strategy B: application server (FastAPI, Express, etc.)
            image = _detect_image_for_start(work_dir, data.framework)
            install_cmd = data.install_command or _default_install(image)
            cmd_str = f"{install_cmd} && {data.start_command}"
            command = [
                "run", "-d",
                "--name",    container_name,
                "--network", TENANT_NETWORK,
                "--restart", "unless-stopped",
                "--cpus",    plan["cpu"],
                "--memory",  plan["memory"],
                "-v", f"{work_dir}:/app",
                "-w", "/app",
                *_docker_env_flags(data.env_vars),
                *_traefik_labels(container_name, subdomain, data.port),
                image, "sh", "-c", cmd_str,
            ]

        else:
            # Strategy C: static or Node build → nginx serve
            pkg: dict = {}
            has_package_json = False
            if os.path.exists(os.path.join(work_dir, "package.json")):
                pkg = _read_pkg(work_dir)
                scripts  = pkg.get("scripts", {})
                all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                has_package_json = (
                    data.build_command is not None or
                    ("build" in scripts and bool(_WEB_BUILDABLE_DEPS & set(all_deps)))
                )
            if not has_package_json and not data.root_directory:
                _candidates = _find_buildable_roots(work_dir)
                if len(_candidates) == 1:
                    _auto_root, pkg = _candidates[0]
                    work_dir   = os.path.join(site_dir, _auto_root) if _auto_root != "." else site_dir
                    _real_work = os.path.realpath(work_dir)
                    has_package_json = True
                    _detected["root_directory"] = _auto_root
                    deploy_log["stages"]["autodetect"] = {"root_directory": _auto_root}
                    logger.info(
                        "github_deploy_stage stage=project_detection autodetected_root=%s repo=%s",
                        _auto_root, data.repo_url,
                    )
                elif len(_candidates) > 1:
                    _opts = [r for r, _ in _candidates]
                    raise DeployError(
                        code=MULTIPLE_PROJECT_ROOTS, stage="project_detection",
                        detail=f"Encontramos varios proyectos posibles: {', '.join(_opts)}.",
                        suggested_fix="Elige Root Directory en la configuración avanzada.",
                        evidence={"candidates": _opts},
                    )
                else:
                    raise DeployError(
                        code=PACKAGE_JSON_NOT_FOUND, stage="project_detection",
                        detail="No encontramos una app web desplegable en este repo.",
                        suggested_fix=(
                            "Verificá que el repositorio contenga un package.json con script build "
                            "y dependencias como react, vite, vue, next o astro. "
                            "Si la app está en una subcarpeta, configurá Root Directory."
                        ),
                    )

            if has_package_json:
                out_dir = data.output_directory or _detect_out_dir(pkg)
                _detected.setdefault("root_directory", data.root_directory or ".")
                _fw = _detect_framework(pkg)
                _detected["framework"]        = _fw
                _detected["output_directory"] = out_dir or "(auto-detect after build)"

                # Preflight: detect incompatible deps/config before running install
                _preflight = run_dependency_preflight(work_dir, pkg)
                if _preflight:
                    raise DeployError(
                        code=_preflight["code"],
                        stage=_preflight.get("stage", "dependency_preflight"),
                        detail=_preflight["detail"],
                        suggested_fix=_preflight["suggested_fix"],
                        evidence={
                            "detected_root_directory": _detected.get("root_directory", "."),
                            "framework": _fw,
                            "node_image": "node:20-alpine",
                            **_preflight["evidence"],
                        },
                    )

                # Package manager detection — preflight passed = exactly one lockfile type
                _pm_info = detect_package_manager(work_dir, pkg)
                _pm = _pm_info["package_manager"]
                if _pm == "pnpm":
                    _pnpm_ver = _pm_info.get("version")
                    _prepare = (
                        f"corepack prepare pnpm@{_pnpm_ver} --activate"
                        if _pnpm_ver else "corepack prepare pnpm --activate"
                    )
                    install_cmd = data.install_command or (
                        f"corepack enable && {_prepare} && pnpm install --frozen-lockfile"
                    )
                    build_cmd = data.build_command or "pnpm run build"
                elif _pm == "yarn":
                    install_cmd = data.install_command or "corepack enable && yarn install --immutable"
                    build_cmd   = data.build_command   or "yarn build"
                else:
                    install_cmd = data.install_command or "npm ci"
                    build_cmd   = data.build_command   or "npm run build"

                deploy_log["stages"]["build_info"] = {
                    "root_directory":   os.path.relpath(work_dir, site_dir),
                    "package_json":     True,
                    "framework":        _fw,
                    "package_manager":  _pm,
                    "install_command":  install_cmd,
                    "build_command":    build_cmd,
                    "output_directory": out_dir or "(auto-detect after build)",
                }
                logger.info(
                    "github_deploy_stage stage=build_info repo=%s root=%s framework=%s pm=%s output=%s",
                    data.repo_url, _detected.get("root_directory"), _fw, _pm, out_dir,
                )

                # Phase 1 — separate install and build with rich diagnostics
                _npm_log_dir = tempfile.mkdtemp(prefix="hg_npm_")
                _native_prefix = (
                    "apk add --no-cache python3 make g++ >/dev/null 2>&1 && "
                    "node --version && npm --version && "
                )
                _env_flags = _safe_build_env_flags(data.env_vars)

                def _node_run(cmd: str, timeout: int = 300) -> subprocess.CompletedProcess:
                    return subprocess.run(
                        ["docker", "run", "--rm",
                         "-v", f"{work_dir}:/app",
                         "-v", f"{_npm_log_dir}:/root/.npm/_logs",
                         "-w", "/app",
                         *_env_flags,
                         "node:20-alpine",
                         "sh", "-c", cmd],
                        capture_output=True, text=True, timeout=timeout,
                    )

                _node_ver: Optional[str] = None
                _npm_ver:  Optional[str] = None

                # Step 1a — npm install
                _install_run = await loop.run_in_executor(
                    None, lambda: _node_run(f"{_native_prefix}{install_cmd}")
                )
                _node_ver, _npm_ver = _parse_versions(_install_run.stdout)
                deploy_log["stages"]["npm_install"] = {
                    "ok":     _install_run.returncode == 0,
                    "stdout": _install_run.stdout[-3000:],
                    "stderr": _install_run.stderr[-3000:],
                }

                if _install_run.returncode != 0:
                    _iout = _install_run.stderr + _install_run.stdout
                    # ERESOLVE peer-dep retry only applies to npm (not pnpm/yarn)
                    if _pm == "npm" and "ERESOLVE" in _iout:
                        _retry_install = await loop.run_in_executor(
                            None,
                            lambda: _node_run(f"{_native_prefix}npm install --legacy-peer-deps"),
                        )
                        deploy_log["stages"]["npm_install_retry"] = {
                            "reason": "ERESOLVE", "cmd": "legacy-peer-deps",
                            "ok": _retry_install.returncode == 0,
                        }
                        _install_run = _retry_install

                if _install_run.returncode != 0:
                    _iout = _install_run.stderr + _install_run.stdout
                    _icode, _idetail, _ifix = classify_npm_failure(_iout, stage="dependency_install")
                    # Map generic fallback to PM-specific code
                    if _icode == "npm_install_failed":
                        _icode = {
                            "pnpm": "pnpm_install_failed",
                            "yarn": "yarn_install_failed",
                        }.get(_pm, "npm_ci_failed")
                    _ilog = read_npm_log(extract_npm_log_path(_iout), _npm_log_dir)
                    raise DeployError(
                        code=_icode, stage="dependency_install",
                        detail=_idetail, suggested_fix=_ifix,
                        technical_detail=_iout[-400:],
                        evidence={
                            "package_manager":   _pm,
                            "install_cmd":       install_cmd,
                            "node_version":      _node_ver,
                            "npm_version":       _npm_ver,
                            "suspected_package": extract_suspected_package(_iout),
                            "stdout_tail":       _install_run.stdout[-2000:],
                            "stderr_tail":       _install_run.stderr[-2000:],
                            **_ilog,
                        },
                    )

                # Step 1b — npm run build
                _build_run = await loop.run_in_executor(
                    None, lambda: _node_run(f"{_native_prefix}{build_cmd}")
                )
                deploy_log["stages"]["build"] = {
                    "ok":     _build_run.returncode == 0,
                    "stdout": _build_run.stdout[-3000:],
                    "stderr": _build_run.stderr[-3000:],
                }

                if _build_run.returncode != 0:
                    _bout = _build_run.stderr + _build_run.stdout
                    if "ERR_OSSL" in _bout:
                        _openssl_cmd = (
                            f"{_native_prefix}"
                            f"NODE_OPTIONS=--openssl-legacy-provider {build_cmd}"
                        )
                        _retry_build = await loop.run_in_executor(
                            None, lambda: _node_run(_openssl_cmd)
                        )
                        deploy_log["stages"]["build_retry"] = {
                            "reason": "ERR_OSSL", "cmd": "openssl-legacy",
                            "ok": _retry_build.returncode == 0,
                        }
                        _build_run = _retry_build

                if _build_run.returncode != 0:
                    _bout = _build_run.stderr + _build_run.stdout
                    _bcode, _bdetail, _bfix = classify_npm_failure(_bout, stage="build")
                    _blog = read_npm_log(extract_npm_log_path(_bout), _npm_log_dir)
                    raise DeployError(
                        code=_bcode, stage="build",
                        detail=_bdetail, suggested_fix=_bfix,
                        technical_detail=_bout[-400:],
                        evidence={
                            "build_cmd":         build_cmd,
                            "node_version":      _node_ver,
                            "npm_version":       _npm_ver,
                            "suspected_package": extract_suspected_package(_bout),
                            "stdout_tail":       _build_run.stdout[-2000:],
                            "stderr_tail":       _build_run.stderr[-2000:],
                            **_blog,
                        },
                    )

                # Phase 2 — find index.html in build output
                if out_dir:
                    _found_dirs = (
                        [out_dir]
                        if os.path.exists(os.path.join(work_dir, out_dir, "index.html"))
                        else []
                    )
                else:
                    _found_dirs = [
                        d for d in ["build", "dist", "out"]
                        if os.path.exists(os.path.join(work_dir, d, "index.html"))
                    ]
                    if _found_dirs:
                        out_dir = _found_dirs[0]

                deploy_log["stages"]["output_check"] = {
                    "output_directory": out_dir,
                    "candidates_found": _found_dirs,
                    "index_html_found": len(_found_dirs) > 0,
                }

                if len(_found_dirs) > 1:
                    raise DeployError(
                        code=MULTIPLE_OUTPUT_DIRECTORIES, stage="artifact_detection",
                        detail=f"Build completado pero se encontraron varios directorios de salida: {', '.join(_found_dirs)}.",
                        suggested_fix="Indicá Output Directory manualmente en la configuración avanzada.",
                        evidence={"checked_paths": _found_dirs},
                    )
                if not _found_dirs:
                    _checked = [
                        os.path.join(os.path.relpath(work_dir, site_dir), d, "index.html")
                        for d in ["build", "dist", "out", "public"]
                    ]
                    _detected["output_directory"] = out_dir or "not_detected"
                    raise DeployError(
                        code=INDEX_HTML_NOT_FOUND, stage="artifact_detection",
                        detail=(
                            f"Build completado pero no se encontró index.html "
                            f"({out_dir or 'ningún directorio de salida detectado'})."
                        ),
                        suggested_fix=(
                            "Create React App genera build/; Vite genera dist/. "
                            "Especifica output_directory en la configuración avanzada."
                        ),
                        evidence={"checked_paths": _checked},
                    )

                # Phase 3 — serve built assets with nginx
                serve_root  = os.path.join(work_dir, out_dir)
                _real_serve = os.path.realpath(serve_root)
                if not (_real_serve == _real_work or _real_serve.startswith(_real_work + os.sep)):
                    await loop.run_in_executor(None, lambda: subprocess.run(["rm", "-rf", site_dir]))
                    raise HTTPException(status_code=400, detail="output_directory no puede salir de root_directory")

                if os.path.exists(os.path.join(serve_root, ".git")):
                    raise DeployError(
                        code=UNSAFE_PUBLISH_ROOT, stage="artifact_detection",
                        detail="El directorio a publicar contiene el repositorio fuente, no el build final.",
                        suggested_fix=(
                            "HostingGuard publica solo la salida del build (ej: build/, dist/). "
                            "Esto no debería ocurrir — contactá soporte."
                        ),
                        evidence={"serve_root": os.path.relpath(serve_root, site_dir), "contains_git": True},
                    )

                _resolved_out_dir = out_dir
                command = [
                    "run", "-d",
                    "--name",    container_name,
                    "--network", TENANT_NETWORK,
                    "--restart", "unless-stopped",
                    "--cpus",    plan["cpu"],
                    "--memory",  plan["memory"],
                    "-v", f"{serve_root}:/usr/share/nginx/html:ro",
                    *_traefik_labels(container_name, subdomain, data.port),
                    "nginx:alpine",
                ]
            else:
                # Pure static — resolve output dir
                serve_root = (
                    os.path.join(work_dir, data.output_directory)
                    if data.output_directory
                    else _find_serve_dir(work_dir)
                )
                if data.output_directory:
                    _real_serve = os.path.realpath(serve_root)
                    if not (_real_serve == _real_work or _real_serve.startswith(_real_work + os.sep)):
                        await loop.run_in_executor(None, lambda: subprocess.run(["rm", "-rf", site_dir]))
                        raise HTTPException(status_code=400, detail="output_directory no puede salir de root_directory")

                if not os.path.exists(os.path.join(serve_root, "index.html")):
                    raise DeployError(
                        code=INDEX_HTML_NOT_FOUND, stage="artifact_detection",
                        detail="No se encontró index.html en el directorio a publicar.",
                        suggested_fix=(
                            "Verificá que el repositorio contenga index.html en la raíz "
                            "o especificá Output Directory en la configuración avanzada."
                        ),
                        evidence={"serve_root": os.path.relpath(serve_root, site_dir)},
                    )
                if os.path.exists(os.path.join(serve_root, ".git")):
                    raise DeployError(
                        code=UNSAFE_PUBLISH_ROOT, stage="artifact_detection",
                        detail="El directorio a publicar contiene el repositorio fuente, no el build final.",
                        suggested_fix=(
                            "No es posible publicar el repositorio completo. "
                            "Especificá el directorio de salida del build en la configuración avanzada."
                        ),
                        evidence={"serve_root": os.path.relpath(serve_root, site_dir), "contains_git": True},
                    )

                deploy_log["stages"]["build_info"] = {
                    "root_directory":   data.root_directory or ".",
                    "package_json":     False,
                    "output_directory": data.output_directory or "(auto-detect)",
                }
                _resolved_out_dir = data.output_directory
                command = [
                    "run", "-d",
                    "--name",    container_name,
                    "--network", TENANT_NETWORK,
                    "--restart", "unless-stopped",
                    "--cpus",    plan["cpu"],
                    "--memory",  plan["memory"],
                    "-v", f"{serve_root}:/usr/share/nginx/html:ro",
                    *_docker_env_flags(data.env_vars),
                    *_traefik_labels(container_name, subdomain, data.port),
                    "nginx:alpine",
                ]

        _detected.setdefault("output_directory", _resolved_out_dir or ".")

        code, _, stderr = await run_docker_command_async(command, timeout=60)
        deploy_log["stages"]["container"] = {"ok": code == 0, "stderr": stderr[-2000:]}
        if code != 0:
            raise DeployError(
                code=CONTAINER_START_FAILED, stage="container_create",
                detail="El contenedor no pudo iniciarse.",
                suggested_fix="Revisa los logs del contenedor. Puede ser un problema de imagen o de puerto.",
                technical_detail=stderr[-400:],
                status_code=500,
            )
        _container_created = True

        # ── Initial health check (before persisting) ──────────────────────────
        # Catches hard HTTP failures (403/404/502/503) that won't resolve later.
        # Skips SSL-related errors (526, TLS, connection) — cert provisioning may
        # still be in progress and will be polled after the row is persisted.
        await asyncio.sleep(2)
        _initial_probe = await check_site_once(subdomain)
        _hc_status = _initial_probe["http_status"] or 0
        if _hc_status in _HC_ERRORS:
            _hc_code, _hc_fix = _HC_ERRORS[_hc_status]
            raise DeployError(
                code=_hc_code, stage="health_check",
                detail=f"El sitio fue creado pero respondió HTTP {_hc_status}.",
                suggested_fix=_hc_fix,
                evidence={"http_status": _hc_status, "subdomain": subdomain, "container_name": container_name},
            )

        # ── Persist to DB ─────────────────────────────────────────────────────
        hosting_id = _hosting_repo.create_hosting(
            user_id=user_id,
            name=data.name,
            subdomain=subdomain,
            container_name=container_name,
            plan=data.plan,
            ip_address=ip_address,
        )
        _hosting_id = hosting_id

        import secrets as _secrets
        webhook_token = _secrets.token_hex(24)
        _strategy = (
            "dockerfile"   if (data.dockerfile_path or data.framework == "dockerfile") else
            "server"       if data.start_command else
            "static_built" if has_package_json else
            "static_pure"
        )
        git_config = {
            "repo_url":         data.repo_url,
            "branch":           data.branch,
            "root_directory":   data.root_directory,
            "install_command":  data.install_command,
            "build_command":    data.build_command,
            "start_command":    data.start_command,
            "output_directory": _resolved_out_dir if _strategy in ("static_built", "static_pure") else data.output_directory,
            "port":             data.port,
            "framework":        data.framework,
            "dockerfile_path":  data.dockerfile_path,
            "env_vars":         data.env_vars,
            "strategy":         _strategy,
        }
        _hosting_repo.set_git_config(hosting_id, git_config, webhook_token)
        deploy_log["finished_at"] = datetime.now().isoformat()
        _hosting_repo.append_deploy_log(hosting_id, deploy_log)

        # ── SSL / liveness poll ───────────────────────────────────────────────
        _ssl_result = await wait_for_site_online(subdomain, timeout_seconds=60, interval_seconds=5)
        _ssl_online = _ssl_result["status"] == "online"

        if _ssl_result["status"] == "http_failed":
            # A hard HTTP error appeared after persist — clean up and fail.
            _hf_status = _ssl_result["last_http_status"] or 0
            _hc_code, _hc_fix = _HC_ERRORS.get(
                _hf_status,
                (SITE_RETURNS_503, "El sitio respondió un error inesperado después de desplegarse."),
            )
            cleanup_status = await _do_cleanup()
            record_deploy_event(
                user_id=user_id, hosting_id=hosting_id,
                repo_url=data.repo_url, branch=data.branch, project_name=project_name,
                stage="health_check", status="failed",
                code=_hc_code, message=f"El sitio respondió HTTP {_hf_status} tras el deploy.",
                suggested_fix=_hc_fix,
                evidence={**_detected, "http_status": _hf_status, "subdomain": subdomain},
                cleanup_status=cleanup_status,
            )
            raise DeployError(
                code=_hc_code, stage="health_check",
                detail=f"El sitio respondió HTTP {_hf_status} tras el deploy.",
                suggested_fix=_hc_fix,
                evidence={"http_status": _hf_status, "subdomain": subdomain, "cleanup_status": cleanup_status},
            )

        _ssl_evidence = {
            **_detected,
            "ssl_status":    "online" if _ssl_online else "pending",
            "ssl_attempts":  _ssl_result["attempts"],
            "ssl_duration_s": round(_ssl_result["duration_seconds"], 1),
        }

        if not _ssl_online:
            record_deploy_event(
                user_id=user_id, hosting_id=hosting_id,
                repo_url=data.repo_url, branch=data.branch, project_name=project_name,
                stage="ssl_check", status="pending",
                code=SSL_PROVISIONING_TIMEOUT,
                message="El certificado SSL aún no está activo. Tomará unos segundos más.",
                suggested_fix="El SSL se activa automáticamente. La página estará disponible en breve.",
                evidence=_ssl_evidence,
            )

        record_deploy_event(
            user_id=user_id, hosting_id=hosting_id,
            repo_url=data.repo_url, branch=data.branch, project_name=project_name,
            stage="success", status="success",
            message="Deploy completado exitosamente.",
            evidence=_ssl_evidence,
        )
        logger.info(
            "github_deploy_stage stage=success repo=%s hosting_id=%s user=%s ssl_status=%s",
            data.repo_url, hosting_id, user_id, "online" if _ssl_online else "pending",
        )

        return {
            "status":        "deployed",
            "type":          "github",
            "hosting_id":    hosting_id,
            "subdomain":     subdomain,
            "url":           f"https://{subdomain}",
            "ssl_status":    "online" if _ssl_online else "pending",
            "message":       "Deploy completado exitosamente." if _ssl_online else "Sitio publicado. SSL activándose.",
            "repo":          data.repo_url,
            "branch":        data.branch,
            "webhook_url":   f"/hosting/hostings/{hosting_id}/webhook",
            "webhook_token": webhook_token,
        }

    except DeployError as de:
        cleanup_status = await _do_cleanup()
        de.evidence["cleanup_status"] = cleanup_status
        record_deploy_event(
            user_id=user_id, hosting_id=None,
            repo_url=data.repo_url, branch=data.branch, project_name=data.name,
            stage=de.stage, status="failed",
            code=de.code, message=de.detail,
            technical_detail=de.technical_detail, suggested_fix=de.suggested_fix,
            evidence={**de.evidence, **_detected},
            cleanup_status=cleanup_status,
        )
        logger.warning(
            "github_deploy_failed stage=%s code=%s repo=%s user=%s",
            de.stage, de.code, data.repo_url, user_id,
        )
        raise
    except HTTPException:
        raise
    except Exception:
        cleanup_status = await _do_cleanup()
        logger.exception(
            "github_deploy_unexpected code=%s repo=%s user=%s",
            UNKNOWN_DEPLOY_ERROR, data.repo_url, user_id,
        )
        raise HTTPException(status_code=500, detail="Error interno inesperado en el deploy.")
