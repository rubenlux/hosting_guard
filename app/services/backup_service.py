"""Backup service — creates MariaDB + files backups for WP sites."""
import io
import json
import logging
import os
import re
import subprocess
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.infra.db import get_connection, release_connection

logger = logging.getLogger(__name__)

BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "/opt/data/backups"))


def _get_db_env(db_container: str) -> dict:
    """Gets MariaDB credentials from container env vars."""
    try:
        r = subprocess.run(
            ["docker", "inspect", "--format",
             "{{range .Config.Env}}{{.}}\n{{end}}", db_container],
            capture_output=True, text=True, timeout=10
        )
        env = {}
        for line in r.stdout.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
        return env
    except Exception:
        return {}


_WEB_ROOT_CANDIDATES = ["/var/www/html", "/app", "/srv/www", "/var/www", "/usr/share/nginx/html"]


def _find_web_root(container: str) -> Optional[str]:
    """Returns the first existing candidate web root directory in the container."""
    for path in _WEB_ROOT_CANDIDATES:
        r = subprocess.run(
            ["docker", "exec", container, "test", "-d", path],
            capture_output=True, timeout=5,
        )
        if r.returncode == 0:
            return path
    return None


def _find_wp_root(container: str) -> Optional[str]:
    """
    Returns WordPress installation directory if this is a WP container, else None.
    Tries wp-cli first (fastest), then searches for wp-config.php.
    """
    r = subprocess.run(
        ["docker", "exec", container, "wp", "--allow-root", "eval", "echo ABSPATH;"],
        capture_output=True, text=True, timeout=10,
    )
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip().rstrip("/")

    # Fallback: look for wp-config.php in common web roots
    for base in _WEB_ROOT_CANDIDATES:
        r2 = subprocess.run(
            ["docker", "exec", container, "test", "-f", f"{base}/wp-config.php"],
            capture_output=True, timeout=5,
        )
        if r2.returncode == 0:
            return base

    return None


def _resolve_db_container(container: str) -> Optional[str]:
    """
    Derives the MariaDB container name.
    New naming: user_{id}_wp_{name}_{uid} → user_{id}_db_{name}_{uid}
    Old naming: reads WORDPRESS_DB_HOST from container env.
    """
    if "_wp_" in container:
        return container.replace("_wp_", "_db_", 1)

    env = _get_db_env(container)
    db_host = env.get("WORDPRESS_DB_HOST") or env.get("MYSQL_HOST")
    if db_host:
        return db_host.split(":")[0]

    return None


def create_backup(hosting_id: int, user_id: int, container: str, db_container: Optional[str],
                  site_name: str, subdomain: str) -> dict:
    """
    Creates a backup for any hosting container.
    - WordPress containers: DB dump (mysqldump) + wp-content tar
    - PHP/other containers: full web root tar (no DB)
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_dir = BACKUP_DIR / str(user_id) / str(hosting_id) / ts
    backup_dir.mkdir(parents=True, exist_ok=True)

    errors = []
    db_size = 0
    files_size = 0

    # Detect site type
    wp_root = _find_wp_root(container)
    is_wordpress = wp_root is not None
    web_root = wp_root if is_wordpress else _find_web_root(container)

    if not web_root:
        errors.append("No se encontró ningún directorio web en el contenedor")
        backup_id = _save_backup_record(
            hosting_id=hosting_id, user_id=user_id,
            site_name=site_name, ts=ts,
            db_path=None, files_path=None,
            size_bytes=0, status="failed",
            errors="; ".join(errors),
        )
        return {"backup_id": backup_id, "ts": ts, "db_path": None, "files_path": None,
                "size_bytes": 0, "errors": errors, "status": "failed"}

    # 1. DB dump — only for WordPress
    db_path = None
    if is_wordpress:
        if not db_container:
            db_container = _resolve_db_container(container)
        if db_container:
            env = _get_db_env(db_container)
            db_name = env.get("MYSQL_DATABASE", "wordpress")
            db_user = env.get("MYSQL_USER", "wordpress")
            db_pass = env.get("MYSQL_PASSWORD", "")
            dump_path = backup_dir / "db.sql.gz"
            r = subprocess.run(
                ["docker", "exec", db_container,
                 "sh", "-c", f"mysqldump -u{db_user} -p{db_pass} {db_name} | gzip"],
                capture_output=True, timeout=120,
            )
            if r.returncode == 0 and r.stdout:
                dump_path.write_bytes(r.stdout)
                db_size = dump_path.stat().st_size
                db_path = str(dump_path)
            else:
                errors.append(f"DB dump failed: {r.stderr.decode(errors='replace')[:120]}")
        else:
            errors.append("DB container no encontrado — solo se respaldarán los archivos")

    # 2. Files tar
    # WordPress: only wp-content (themes, plugins, uploads)
    # PHP hosting: full web root
    files_path = None
    archive_name = "wp-content.tar.gz" if is_wordpress else "files.tar.gz"
    tar_subdir = "wp-content" if is_wordpress else "."
    content_tar = backup_dir / archive_name
    r2 = subprocess.run(
        ["docker", "exec", container,
         "tar", "-czf", "-", "-C", web_root, tar_subdir],
        capture_output=True, timeout=180,
    )
    if r2.returncode == 0 and r2.stdout:
        content_tar.write_bytes(r2.stdout)
        files_size = content_tar.stat().st_size
        files_path = str(content_tar)
    else:
        errors.append(f"Files backup failed: {r2.stderr.decode(errors='replace')[:120]}")

    total_size = db_size + files_size

    # 3. Store in DB
    backup_id = _save_backup_record(
        hosting_id=hosting_id, user_id=user_id,
        site_name=site_name, ts=ts,
        db_path=db_path, files_path=files_path,
        size_bytes=total_size,
        status="completed" if not errors else "partial",
        errors="; ".join(errors) if errors else None,
    )

    return {
        "backup_id": backup_id,
        "ts": ts,
        "db_path": db_path,
        "files_path": files_path,
        "size_bytes": total_size,
        "errors": errors,
        "status": "completed" if not errors else "partial",
    }


def _save_backup_record(hosting_id, user_id, site_name, ts, db_path, files_path,
                         size_bytes, status, errors=None) -> int:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO backups
               (hosting_id, user_id, site_name, created_at, db_path, files_path,
                size_bytes, status, error_message)
               VALUES (%s,%s,%s,NOW(),%s,%s,%s,%s,%s)
               RETURNING backup_id""",
            (hosting_id, user_id, site_name, db_path, files_path,
             size_bytes, status, errors),
        )
        row = cur.fetchone()
        conn.commit()
        return row["backup_id"] if row else 0
    except Exception:
        conn.rollback()
        raise
    finally:
        release_connection(conn)


def list_backups(hosting_id: int, user_id: int) -> list:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT backup_id, hosting_id, site_name, created_at, size_bytes, status, error_message
               FROM backups WHERE hosting_id=%s AND user_id=%s
               ORDER BY created_at DESC LIMIT 20""",
            (hosting_id, user_id),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        release_connection(conn)


def auto_backup_all() -> None:
    """Scheduled job — creates nightly backups for all active WP sites."""
    from app.infra.db import reset_pg_connection
    from app.infra.audit.hosting_repository import HostingRepository
    from app.services.notification_service import notify

    reset_pg_connection()
    repo = HostingRepository()
    hostings = repo.get_all_hostings()
    wp_active = [h for h in hostings if h.get("status") == "active" and "_wp_" in h.get("container_name", "")]
    logger.info("auto_backup: starting for %d WP sites", len(wp_active))

    for hosting in wp_active:
        hosting_id = hosting["hosting_id"]
        user_id = hosting["user_id"]
        container = hosting["container_name"]
        site_name = hosting.get("name") or str(hosting_id)
        subdomain = hosting.get("subdomain", "")

        try:
            notify(user_id, f"Backup iniciado: {site_name}",
                   f"El backup automático de '{site_name}' fue iniciado.",
                   category="backup", severity="info", channel="dashboard")

            result = create_backup(hosting_id, user_id, container, None, site_name, subdomain)

            if result["status"] == "completed":
                size_mb = result["size_bytes"] / (1024 * 1024)
                notify(user_id, f"Backup completado: {site_name}",
                       f"Backup de '{site_name}' completado ({size_mb:.1f} MB). "
                       "DB y archivos wp-content respaldados.",
                       category="backup", severity="success", channel="dashboard")
            else:
                notify(user_id, f"Backup parcial: {site_name}",
                       f"El backup de '{site_name}' tuvo errores: {'; '.join(result['errors'])[:200]}",
                       category="backup", severity="warning", channel="both")
        except Exception as exc:
            logger.error("auto_backup: failed for hosting %s: %s", hosting_id, exc)
            try:
                notify(user_id, f"Backup fallido: {site_name}",
                       f"El backup automático de '{site_name}' falló: {str(exc)[:150]}",
                       category="backup", severity="critical", channel="both")
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# Lookup helpers
# ─────────────────────────────────────────────────────────────────────────────

def _safe_path(raw: Optional[str]) -> Optional[Path]:
    """Return Path only if it sits inside BACKUP_DIR. Prevents path traversal."""
    if not raw:
        return None
    p = Path(raw).resolve()
    try:
        p.relative_to(BACKUP_DIR.resolve())
        return p
    except ValueError:
        logger.warning("backup: rejected out-of-tree path %s", raw)
        return None


def get_backup(backup_id: int, user_id: int) -> Optional[dict]:
    """Fetch one backup enforcing ownership (user_id must match)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM backups WHERE backup_id=%s AND user_id=%s",
            (backup_id, user_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        release_connection(conn)


def admin_get_backup(backup_id: int) -> Optional[dict]:
    """Fetch one backup without ownership check — admin use only."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM backups WHERE backup_id=%s", (backup_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        release_connection(conn)


def admin_list_backups(user_id: Optional[int] = None,
                       hosting_id: Optional[int] = None,
                       limit: int = 50) -> list:
    """List backups for admin — filter by user and/or hosting, no ownership check."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        clauses, params = [], []
        if user_id is not None:
            clauses.append("user_id=%s"); params.append(user_id)
        if hosting_id is not None:
            clauses.append("hosting_id=%s"); params.append(hosting_id)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        cur.execute(
            f"""SELECT backup_id, hosting_id, user_id, site_name, created_at,
                       size_bytes, status, error_message, db_path, files_path
                FROM backups {where}
                ORDER BY created_at DESC LIMIT %s""",
            params,
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        release_connection(conn)


# ─────────────────────────────────────────────────────────────────────────────
# Download package builder
# ─────────────────────────────────────────────────────────────────────────────

_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]")


def build_download_package(backup: dict) -> tuple:
    """
    Build a temporary tar.gz bundle containing manifest.json + backup files.
    Returns (tmp_path: Path, filename: str). Caller must unlink tmp_path when done.
    """
    site_name = backup.get("site_name") or f"hosting-{backup['hosting_id']}"
    safe_name = _SAFE_NAME_RE.sub("-", site_name)

    created = backup.get("created_at")
    if hasattr(created, "strftime"):
        ts_str = created.strftime("%Y%m%d-%H%M%S")
    else:
        ts_str = re.sub(r"[^0-9]", "", str(created))[:14]
        if len(ts_str) >= 8:
            ts_str = f"{ts_str[:8]}-{ts_str[8:14]}"

    filename = f"hostingguard-backup-{safe_name}-{ts_str}.tar.gz"

    db_p     = _safe_path(backup.get("db_path"))
    files_p  = _safe_path(backup.get("files_path"))
    has_db   = db_p is not None and db_p.exists()
    has_files = files_p is not None and files_p.exists()

    bundle_files = []
    if has_db:
        bundle_files.append("db.sql.gz")
    if has_files:
        bundle_files.append(files_p.name)  # "wp-content.tar.gz" or "files.tar.gz"

    manifest = {
        "backup_version": "1.0",
        "site_name": site_name,
        "hosting_id": backup["hosting_id"],
        "user_id": backup["user_id"],
        "created_at": str(created),
        "type": "wordpress" if has_db else "static",
        "contains_database": has_db,
        "contains_files": has_files,
        "files": bundle_files + ["manifest.json"],
    }
    manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode()

    tmp = Path(tempfile.mktemp(suffix=".tar.gz", dir="/tmp"))
    with tarfile.open(tmp, "w:gz") as tar:
        info = tarfile.TarInfo(name="manifest.json")
        info.size = len(manifest_bytes)
        tar.addfile(info, io.BytesIO(manifest_bytes))
        if has_db:
            tar.add(str(db_p), arcname="db.sql.gz")
        if has_files:
            tar.add(str(files_p), arcname=files_p.name)

    return tmp, filename


# ─────────────────────────────────────────────────────────────────────────────
# Delete backup
# ─────────────────────────────────────────────────────────────────────────────

def _remove_file_safe(path_str: Optional[str]) -> None:
    p = _safe_path(path_str)
    if p and p.exists():
        p.unlink()
        # Remove empty parent timestamp directory
        try:
            if not any(p.parent.iterdir()):
                p.parent.rmdir()
        except Exception:
            pass


def delete_backup(backup_id: int, user_id: Optional[int] = None,
                  admin: bool = False) -> bool:
    """
    Delete a backup record and its physical files.

    - user_id is required when admin=False (enforces ownership).
    - admin=True skips the ownership check (pass admin_id as user_id for audit).
    - Returns True if a record was found and deleted, False if not found.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        if admin:
            cur.execute(
                "SELECT * FROM backups WHERE backup_id=%s", (backup_id,)
            )
        else:
            cur.execute(
                "SELECT * FROM backups WHERE backup_id=%s AND user_id=%s",
                (backup_id, user_id),
            )
        row = cur.fetchone()
        if not row:
            return False

        backup = dict(row)
        _remove_file_safe(backup.get("db_path"))
        _remove_file_safe(backup.get("files_path"))

        cur.execute("DELETE FROM backups WHERE backup_id=%s", (backup_id,))
        conn.commit()
        logger.info(
            "backup deleted: backup_id=%s hosting_id=%s user_id=%s by_admin=%s",
            backup_id, backup["hosting_id"], backup["user_id"], admin,
        )
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        release_connection(conn)


# ─────────────────────────────────────────────────────────────────────────────
# Cleanup stale failed/partial backups (scheduled job)
# ─────────────────────────────────────────────────────────────────────────────

def cleanup_stale_backups(days: int = 7) -> dict:
    """
    Delete backups with status 'failed' or 'partial' older than `days` days.
    Physical files are removed first; then the DB record is hard-deleted.
    Returns {"deleted": int, "errors": int}.
    """
    from app.infra.db import reset_pg_connection
    reset_pg_connection()

    conn = get_connection()
    deleted = errors = 0
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT backup_id, db_path, files_path FROM backups
               WHERE status IN ('failed','partial')
                 AND created_at < NOW() - INTERVAL '%s days'""",
            (days,),
        )
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        release_connection(conn)

    for row in rows:
        try:
            _remove_file_safe(row.get("db_path"))
            _remove_file_safe(row.get("files_path"))
            conn2 = get_connection()
            try:
                c2 = conn2.cursor()
                c2.execute("DELETE FROM backups WHERE backup_id=%s", (row["backup_id"],))
                conn2.commit()
                deleted += 1
            except Exception:
                conn2.rollback()
                errors += 1
            finally:
                release_connection(conn2)
        except Exception as exc:
            logger.error("cleanup_stale_backups: error on backup_id=%s: %s", row["backup_id"], exc)
            errors += 1

    logger.info("cleanup_stale_backups: deleted=%d errors=%d (threshold=%d days)", deleted, errors, days)
    return {"deleted": deleted, "errors": errors}
