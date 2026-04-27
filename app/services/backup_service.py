"""Backup service — creates MariaDB + files backups for WP sites."""
import logging
import os
import subprocess
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
