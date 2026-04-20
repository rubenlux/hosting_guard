"""
WordPress backup import pipeline.

Supported formats:
  WPRESS  — All-in-One WP Migration .wpress export
  ZIP_WP  — ZIP containing wp-content/ and optionally a .sql file
  SQL     — Plain SQL dump (DB only, files restored separately)

Pipeline states (stored in import_jobs.status):
  uploading → processing → restoring_files → restoring_db → fixing_urls → completed | failed
"""
import asyncio
import logging
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.api.security import verify_token
from app.infra.audit.hosting_repository import HostingRepository
from app.infra.audit.import_repository import ImportRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hosting", tags=["Import"])

_import_repo = ImportRepository()
_hosting_repo = HostingRepository()

MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB
ALLOWED_EXTENSIONS = {".zip", ".wpress", ".sql"}
UPLOAD_DIR = Path(os.getenv("IMPORT_UPLOAD_DIR", "/tmp/hg_imports"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ── helpers ──────────────────────────────────────────────────────────────────

def _docker(*args, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker"] + list(args),
        capture_output=True, text=True, timeout=timeout,
    )


def _docker_exec(container: str, *cmd, timeout: int = 120) -> subprocess.CompletedProcess:
    return _docker("exec", container, *cmd, timeout=timeout)


def _log(job_id: int, line: str):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    _import_repo.append_log(job_id, f"[{ts}] {line}")
    logger.info("[import:%d] %s", job_id, line)


def _detect_type(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".wpress"):
        return "WPRESS"
    if name.endswith(".sql"):
        return "SQL"
    if name.endswith(".zip"):
        try:
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
            if any("wp-content/" in n for n in names):
                return "ZIP_WP"
            if any(n.endswith(".sql") for n in names):
                return "ZIP_SQL"
        except Exception:
            pass
        return "ZIP_GENERIC"
    return "UNKNOWN"


_PLAN_RESOURCES: dict = {
    "free":     {"cpu": "0.25", "memory": "256m"},
    "personal": {"cpu": "0.5",  "memory": "512m"},
    "negocio":  {"cpu": "1",    "memory": "1g"},
    "agencia":  {"cpu": "2",    "memory": "2g"},
}


def _container_exists(name: str) -> bool:
    r = _docker("inspect", "--format", "{{.State.Status}}", name, timeout=10)
    return r.returncode == 0


def _get_container_env(container: str, key: str) -> Optional[str]:
    r = _docker("inspect", "--format", "{{range .Config.Env}}{{println .}}{{end}}", container, timeout=10)
    if r.returncode != 0:
        return None
    for line in r.stdout.splitlines():
        if line.startswith(f"{key}="):
            return line[len(key) + 1:]
    return None


def _get_container_network(container: str) -> str:
    r = _docker(
        "inspect", "--format",
        "{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}",
        container, timeout=10,
    )
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip().split()[0]
    return "deploy_hosting_network"


def _wait_for_db(job_id: int, db_container: str, db_password: str, max_wait: int = 60) -> None:
    """Block until MariaDB accepts connections or raise RuntimeError."""
    import time
    for _ in range(max_wait // 3):
        r = _docker_exec(
            db_container,
            "mysqladmin", "ping", f"-uroot", f"-p{db_password}", "--silent",
            timeout=5,
        )
        if r.returncode == 0:
            _log(job_id, "[import] DB container ready")
            return
        time.sleep(3)
    raise RuntimeError(f"DB container {db_container} no respondió en {max_wait}s — import abortado")


def _ensure_db_container(job_id: int, wp_container: str, db_container: str, plan: str) -> str:
    """
    Idempotent: ensure the MariaDB container paired with wp_container exists and is ready.
    Returns the db_password (extracted from wp_container env or from existing db_container).
    """
    if _container_exists(db_container):
        _log(job_id, f"[import] DB container {db_container} already exists")
        db_password = _get_container_env(db_container, "MYSQL_PASSWORD") or ""
        return db_password

    _log(job_id, f"[import] Creating DB container {db_container}...")

    db_password = _get_container_env(wp_container, "WORDPRESS_DB_PASSWORD")
    if not db_password:
        raise RuntimeError(
            f"No se pudo obtener WORDPRESS_DB_PASSWORD del container {wp_container}. "
            "Verifica que el hosting fue creado correctamente."
        )

    network = _get_container_network(wp_container)
    _log(job_id, f"[import] Using network: {network}")

    resources = _PLAN_RESOURCES.get(plan, _PLAN_RESOURCES["free"])

    r = _docker(
        "run", "-d",
        "--name",    db_container,
        "--network", network,
        "-e", f"MYSQL_ROOT_PASSWORD={db_password}",
        "-e", "MYSQL_DATABASE=wordpress",
        "-e", "MYSQL_USER=wpuser",
        "-e", f"MYSQL_PASSWORD={db_password}",
        "--cpus",    resources["cpu"],
        "--memory",  resources["memory"],
        "mariadb:10.11",
        timeout=30,
    )
    if r.returncode != 0:
        raise RuntimeError(f"No se pudo crear DB container: {r.stderr.strip()}")

    _log(job_id, "[import] DB container created, waiting for readiness...")
    _wait_for_db(job_id, db_container, db_password)
    _log(job_id, "[import] DB container ready")
    return db_password


def _wait_for_wp(container: str, max_wait: int = 120) -> bool:
    """Wait until WordPress is fully initialised inside the container."""
    for _ in range(max_wait // 5):
        r = _docker_exec(container, "wp", "--allow-root", "--info", timeout=10)
        if r.returncode == 0:
            return True
        asyncio.get_event_loop().run_until_complete(asyncio.sleep(5))  # noqa: blocking ok in executor
        import time; time.sleep(5)
    return False


# ── pipeline ─────────────────────────────────────────────────────────────────

def _run_pipeline(job_id: int, hosting_id: int, user_id: int, file_path: Path, sql_path: Optional[Path] = None):
    """Blocking pipeline — called from a thread executor so the event loop is free."""
    try:
        _import_repo.set_status(job_id, "processing")
        _log(job_id, f"Archivo recibido: {file_path.name} ({file_path.stat().st_size // 1024} KB)")

        # ── Resolve container ─────────────────────────────────────────────
        hosting = _hosting_repo.get_hosting_any(hosting_id)
        if not hosting:
            raise RuntimeError(f"Hosting {hosting_id} no encontrado")
        container = hosting["container_name"]
        subdomain = hosting.get("subdomain", "")
        # subdomain is stored as full domain (e.g. "site.hostingguard.lat")
        new_domain = subdomain

        # Detect DB container (naming convention: replace _wp_ with _db_)
        db_container = container.replace("_wp_", "_db_") if "_wp_" in container else None
        _log(job_id, f"Container destino: {container}")
        _log(job_id, f"Dominio nuevo: {new_domain}")

        # ── Ensure DB container exists and is ready ───────────────────────
        if db_container:
            plan = hosting.get("plan", "free")
            _ensure_db_container(job_id, container, db_container, plan)
        else:
            _log(job_id, "WARN: No se pudo determinar el container DB (nombre WP sin '_wp_')")

        # ── Detect backup type ────────────────────────────────────────────
        btype = _detect_type(file_path)
        _log(job_id, f"Tipo de backup detectado: {btype}")
        _import_repo.set_status(job_id, "restoring_files")

        if btype == "WPRESS":
            _restore_wpress(job_id, container, file_path)
        elif btype in ("ZIP_WP", "ZIP_GENERIC"):
            _restore_zip_wp(job_id, container, db_container, file_path)
        elif btype == "ZIP_SQL":
            _restore_zip_sql(job_id, container, db_container, file_path)
        elif btype == "SQL":
            _restore_sql(job_id, db_container, file_path)
        else:
            raise RuntimeError(f"Formato de backup no soportado: {btype}")

        # ── Optional separate SQL file ────────────────────────────────────
        if sql_path and db_container:
            _import_repo.set_status(job_id, "restoring_db")
            _log(job_id, f"Importando SQL separado: {sql_path.name}...")
            _restore_sql_file_to_container(job_id, db_container, sql_path)

        # ── Fix URLs ──────────────────────────────────────────────────────
        _import_repo.set_status(job_id, "fixing_urls")
        old_domain = _detect_old_domain(db_container)
        _log(job_id, f"Dominio original detectado: {old_domain or 'no detectado'}")
        _import_repo.set_domains(job_id, old_domain or "", new_domain)

        if db_container:
            if old_domain and old_domain != new_domain:
                _fix_domain(job_id, db_container, old_domain, new_domain)
            else:
                _log(job_id, "Forzando siteurl/home directamente en BD...")
                for opt in ("siteurl", "home"):
                    _mysql_exec(
                        db_container,
                        f"UPDATE wp_options SET option_value='https://{new_domain}' WHERE option_name='{opt}';",
                        timeout=15,
                    )
        else:
            _log(job_id, "WARN: sin DB container — fix de dominio omitido")

        # ── Permissions ───────────────────────────────────────────────────
        _log(job_id, "Ajustando permisos...")
        _docker_exec(container, "chown", "-R", "www-data:www-data", "/var/www/html")

        # ── Emit event ────────────────────────────────────────────────────
        _hosting_repo.log_orchestrator_event(
            container, user_id, "import_completed",
            f"Backup importado exitosamente. Tipo: {btype}. Dominio: {old_domain} → {new_domain}",
            simulated=False,
        )

        _import_repo.set_status(job_id, "completed")
        _log(job_id, f"✓ Importación completada. Sitio disponible en https://{new_domain}")

    except Exception as exc:
        logger.exception("[import:%d] pipeline failed", job_id)
        _import_repo.set_status(job_id, "failed", error=str(exc))
        _log(job_id, f"✗ Error: {exc}")
        try:
            _hosting_repo.log_orchestrator_event(
                "", user_id, "import_failed", str(exc), simulated=False
            )
        except Exception:
            pass
    finally:
        try:
            file_path.unlink(missing_ok=True)
        except Exception:
            pass
        if sql_path:
            try:
                sql_path.unlink(missing_ok=True)
            except Exception:
                pass


# ── restoration strategies ────────────────────────────────────────────────────

def _restore_wpress(job_id: int, container: str, file_path: Path):
    """Restore a .wpress All-in-One WP Migration backup."""
    _log(job_id, "Instalando plugin all-in-one-wp-migration...")
    r = _docker_exec(
        container, "wp", "--allow-root",
        "plugin", "install", "all-in-one-wp-migration", "--activate",
        timeout=180,
    )
    if r.returncode != 0:
        _log(job_id, f"WARN: instalación plugin: {r.stderr.strip()}")

    backup_dir = "/var/www/html/wp-content/ai1wm-backups"
    _docker_exec(container, "mkdir", "-p", backup_dir)

    dest = f"{backup_dir}/{file_path.name}"
    _log(job_id, "Copiando backup al container...")
    r = _docker("cp", str(file_path), f"{container}:{dest}", timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"docker cp falló: {r.stderr.strip()}")

    _log(job_id, "Ejecutando importación WPRESS (wp ai1wm restore)...")
    r = _docker_exec(
        container, "wp", "--allow-root",
        "ai1wm", "restore", file_path.name, "--yes",
        timeout=600,
    )
    _log(job_id, r.stdout.strip() or "(sin output)")
    if r.returncode != 0:
        _log(job_id, f"WARN restore stderr: {r.stderr.strip()}")
        # Non-fatal: plugin may still have restored most content

    _docker_exec(container, "rm", "-f", dest)


def _restore_zip_wp(job_id: int, container: str, db_container: Optional[str], file_path: Path):
    """Restore a ZIP containing wp-content/ and optionally a .sql dump."""
    import time

    work_dir = UPLOAD_DIR / f"extract_{file_path.stem}"
    work_dir.mkdir(exist_ok=True)

    try:
        _log(job_id, "Extrayendo ZIP...")
        with zipfile.ZipFile(file_path) as zf:
            total = sum(i.file_size for i in zf.infolist())
            if total > 2 * 1024 * 1024 * 1024:  # 2 GB extracted limit
                raise RuntimeError("Backup demasiado grande (> 2GB extraído)")
            zf.extractall(work_dir)

        # Find wp-content dir
        wp_content = next(work_dir.rglob("wp-content"), None)
        if wp_content and wp_content.is_dir():
            _log(job_id, "Copiando wp-content al container...")
            r = _docker("cp", str(wp_content), f"{container}:/var/www/html/", timeout=300)
            if r.returncode != 0:
                raise RuntimeError(f"docker cp wp-content falló: {r.stderr}")

        # Find and restore SQL
        sql_files = list(work_dir.rglob("*.sql"))
        if sql_files and db_container:
            _import_repo.set_status(job_id, "restoring_db")
            _log(job_id, f"Restaurando DB desde {sql_files[0].name}...")
            _restore_sql_file_to_container(job_id, db_container, sql_files[0])
        elif sql_files:
            _log(job_id, "WARN: SQL encontrado pero sin container DB — omitiendo")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _restore_zip_sql(job_id: int, container: str, db_container: Optional[str], file_path: Path):
    """ZIP that only contains a SQL dump."""
    work_dir = UPLOAD_DIR / f"extract_{file_path.stem}"
    work_dir.mkdir(exist_ok=True)
    try:
        with zipfile.ZipFile(file_path) as zf:
            zf.extractall(work_dir)
        sql_files = list(work_dir.rglob("*.sql"))
        if not sql_files:
            raise RuntimeError("No se encontró archivo .sql dentro del ZIP")
        if db_container:
            _import_repo.set_status(job_id, "restoring_db")
            _restore_sql_file_to_container(job_id, db_container, sql_files[0])
        else:
            _log(job_id, "WARN: sin container DB — omitiendo restauración SQL")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _restore_sql(job_id: int, db_container: Optional[str], file_path: Path):
    """Plain SQL dump."""
    _import_repo.set_status(job_id, "restoring_db")
    if not db_container:
        _log(job_id, "WARN: sin container DB — omitiendo restauración SQL")
        return
    _restore_sql_file_to_container(job_id, db_container, file_path)


def _restore_sql_file_to_container(job_id: int, db_container: str, sql_path: Path):
    """Stream SQL file directly via stdin — avoids docker cp (blocked by socket proxy)."""
    _log(job_id, f"Importando SQL en MariaDB ({sql_path.stat().st_size // 1024} KB)...")
    with open(sql_path, "rb") as fh:
        r = subprocess.run(
            ["docker", "exec", "-i", db_container,
             "sh", "-c", 'mysql -u wpuser -p"$MYSQL_PASSWORD" wordpress'],
            stdin=fh,
            capture_output=True,
            timeout=300,
        )
    if r.returncode != 0:
        err = r.stderr.decode(errors="replace").strip()[:400]
        raise RuntimeError(f"mysql import falló: {err}")
    _log(job_id, "SQL importado correctamente")


# ── domain detection & fix ────────────────────────────────────────────────────

def _mysql_exec(db_container: str, sql: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a SQL statement against the wordpress DB inside db_container."""
    return _docker_exec(
        db_container, "sh", "-c",
        f'mysql -u wpuser -p"$MYSQL_PASSWORD" wordpress -e "{sql}"',
        timeout=timeout,
    )


def _detect_old_domain(db_container: Optional[str]) -> Optional[str]:
    """Read siteurl from wp_options via MySQL (wordpress:latest has no WP-CLI)."""
    if not db_container:
        return None
    r = _mysql_exec(
        db_container,
        "SELECT option_value FROM wp_options WHERE option_name='siteurl' LIMIT 1;",
        timeout=15,
    )
    if r.returncode == 0 and r.stdout.strip():
        url = r.stdout.strip().splitlines()[-1].rstrip("/")
        url = re.sub(r"^https?://", "", url)
        return url or None
    return None


def _fix_domain(job_id: int, db_container: str, old_domain: str, new_domain: str):
    """Replace old domain with new domain in wp DB tables via MySQL."""
    _log(job_id, f"Actualizando dominio en BD: {old_domain} → {new_domain}")

    for old_scheme in (f"https://{old_domain}", f"http://{old_domain}"):
        new_url = f"https://{new_domain}"
        for table, col in (
            ("wp_options",  "option_value"),
            ("wp_posts",    "post_content"),
            ("wp_posts",    "guid"),
            ("wp_postmeta", "meta_value"),
        ):
            sql = f"UPDATE {table} SET {col}=REPLACE({col},'{old_scheme}','{new_url}');"
            r = _mysql_exec(db_container, sql, timeout=60)
            if r.returncode == 0:
                _log(job_id, f"  ✓ {table}.{col}")
            else:
                _log(job_id, f"  WARN {table}.{col}: {r.stderr.strip()[:100]}")

    # Force siteurl / home as safety net
    for opt in ("siteurl", "home"):
        _mysql_exec(
            db_container,
            f"UPDATE wp_options SET option_value='https://{new_domain}' WHERE option_name='{opt}';",
            timeout=15,
        )
    _log(job_id, "Dominio actualizado en BD")


# ── endpoints ─────────────────────────────────────────────────────────────────

async def _save_upload(upload: UploadFile, dest: Path, job_id: int) -> int:
    """Stream an uploaded file to disk. Returns bytes written."""
    total = 0
    with open(dest, "wb") as fh:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                fh.close()
                dest.unlink(missing_ok=True)
                _import_repo.set_status(job_id, "failed", "Archivo demasiado grande (máx 500MB)")
                raise HTTPException(status_code=413, detail="Archivo demasiado grande (máx 500MB)")
            fh.write(chunk)
    return total


@router.post("/import")
async def import_site(
    hosting_id: int = Form(...),
    file: UploadFile = File(...),
    sql_file: Optional[UploadFile] = File(None),
    user: dict = Depends(verify_token),
):
    user_id = user["user_id"]

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato no soportado. Permitidos: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    if sql_file and sql_file.filename:
        sql_suffix = Path(sql_file.filename).suffix.lower()
        if sql_suffix != ".sql":
            raise HTTPException(status_code=400, detail="El archivo SQL adicional debe tener extensión .sql")

    hosting = _hosting_repo.get_hosting(hosting_id, user_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting no encontrado")

    job_id = _import_repo.create_job(hosting_id, user_id)

    # Save main file
    dest = UPLOAD_DIR / f"job_{job_id}{suffix}"
    try:
        total = await _save_upload(file, dest, job_id)
    except HTTPException:
        raise
    except Exception as exc:
        dest.unlink(missing_ok=True)
        _import_repo.set_status(job_id, "failed", str(exc))
        raise HTTPException(status_code=500, detail=f"Error al guardar archivo: {exc}")

    _log(job_id, f"Archivo guardado ({total // 1024} KB).")

    # Save optional SQL file
    sql_dest: Optional[Path] = None
    if sql_file and sql_file.filename:
        sql_dest = UPLOAD_DIR / f"job_{job_id}_extra.sql"
        try:
            sql_total = await _save_upload(sql_file, sql_dest, job_id)
            _log(job_id, f"SQL adicional guardado ({sql_total // 1024} KB).")
        except HTTPException:
            dest.unlink(missing_ok=True)
            raise
        except Exception as exc:
            dest.unlink(missing_ok=True)
            sql_dest.unlink(missing_ok=True)
            _import_repo.set_status(job_id, "failed", str(exc))
            raise HTTPException(status_code=500, detail=f"Error al guardar SQL: {exc}")

    _log(job_id, "Iniciando pipeline...")
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, _run_pipeline, job_id, hosting_id, user_id, dest, sql_dest)

    return {
        "job_id": job_id,
        "status": "uploading",
        "message": "Importación iniciada. Consultá /hosting/import/{job_id} para el estado.",
    }


@router.get("/import/{job_id}")
def get_import_status(job_id: int, user: dict = Depends(verify_token)):
    job = _import_repo.get_job(job_id, user_id=user["user_id"])
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    return {
        "job_id":          job["job_id"],
        "hosting_id":      job["hosting_id"],
        "status":          job["status"],
        "backup_type":     job.get("backup_type"),
        "original_domain": job.get("original_domain"),
        "new_domain":      job.get("new_domain"),
        "error":           job.get("error"),
        "created_at":      job.get("created_at"),
        "updated_at":      job.get("updated_at"),
    }


@router.get("/import/{job_id}/logs")
async def stream_import_logs(job_id: int, user: dict = Depends(verify_token)):
    """Server-Sent Events stream of import logs."""
    job = _import_repo.get_job(job_id, user_id=user["user_id"])
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado")

    async def _sse() -> AsyncIterator[str]:
        seen = 0
        finished_statuses = {"completed", "failed"}
        while True:
            j = _import_repo.get_job(job_id)
            logs: str = j.get("logs") or ""
            status: str = j.get("status") or ""
            new_content = logs[seen:]
            if new_content:
                for line in new_content.splitlines():
                    yield f"data: {line}\n\n"
                seen = len(logs)
            if status in finished_statuses:
                yield f"event: status\ndata: {status}\n\n"
                break
            await asyncio.sleep(1)

    return StreamingResponse(
        _sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/import")
def list_import_jobs(
    hosting_id: Optional[int] = None,
    user: dict = Depends(verify_token),
):
    return _import_repo.list_jobs(user["user_id"], hosting_id=hosting_id)
