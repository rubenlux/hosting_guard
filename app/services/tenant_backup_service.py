"""
P3A Tenant Backup Service — local storage, plan-gated, latest-only retention.

Backs up static tenant files from host path /opt/clients/<container_name>
and MariaDB via docker exec mariadb-dump. No S3 in P3A.

Storage layout:
  /opt/hostingguard-backups/
    tenants/<hosting_id>/
      automatic/<backup_id>/  files.tar.gz  database.sql.gz  manifest.json
      manual/<backup_id>/     ...
      internal/<backup_id>/   ...  (pre_restore, pre_delete, system)

Retention:
  automatic  → latest_only (delete previous after new completed)
  manual     → max BACKUP_MAX_MANUAL_BACKUPS_PER_TENANT per tenant
  internal   → TTL BACKUP_PRE_RESTORE_TTL_HOURS
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── patchable constants (overridden in tests) ─────────────────────────────────
_CLIENTS_DIR = os.getenv("CLIENTS_DIR", "/opt/clients")

# ── Entitlement tables ────────────────────────────────────────────────────────

# Plans that get automatic daily backups included
_AUTOMATIC_PLANS = {"agencia_pro", "enterprise", "enterprise_annual", "enterprise_monthly"}
# Plans that get manual backups included
_MANUAL_PLANS = {"negocio", "agencia", "agencia_pro", "enterprise", "enterprise_annual", "enterprise_monthly"}
# Max manual backups per plan
_MAX_MANUAL: dict[str, int] = {
    "free": 0,
    "personal": 0,
    "negocio": 1,
    "agencia": 2,
    "agencia_pro": 2,
    "enterprise": 2,
    "enterprise_annual": 2,
    "enterprise_monthly": 2,
}

# Pre-restore / pre-delete triggers always allowed (internal safety snapshot)
_INTERNAL_TRIGGERS = {"pre_restore", "pre_delete", "system"}


# ── Config ────────────────────────────────────────────────────────────────────

def _cfg(key: str, default: str) -> str:
    return os.getenv(key, default)


def _backup_local_dir() -> Path:
    return Path(_cfg("BACKUP_LOCAL_DIR", "/opt/hostingguard-backups"))


def _backup_enabled() -> bool:
    return _cfg("BACKUP_ENABLED", "true").lower() == "true"


def _max_manual() -> int:
    try:
        return int(_cfg("BACKUP_MAX_MANUAL_BACKUPS_PER_TENANT", "2"))
    except ValueError:
        return 2


def _pre_restore_ttl_hours() -> int:
    try:
        return int(_cfg("BACKUP_PRE_RESTORE_TTL_HOURS", "24"))
    except ValueError:
        return 24


# ── Exclude patterns for file backup ─────────────────────────────────────────

_EXCLUDE_NAMES = frozenset({
    "_upload.zip", "_extracted", "_backup", "_new",
    ".git", "node_modules",
})


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_conn():
    from app.infra.db import get_connection
    return get_connection()


def _rel(conn):
    from app.infra.db import release_connection
    release_connection(conn)


def _audit(event_type: str, hosting_id: Optional[int] = None,
           user_id: Optional[int] = None, metadata: Optional[dict] = None) -> None:
    try:
        from app.services.activity_service import log_event
        log_event(
            user_id=user_id,
            hosting_id=hosting_id,
            actor_type="system",
            event_type=event_type,
            category="backup",
            severity="info",
            title=event_type.replace(".", " ").replace("_", " "),
            metadata=metadata or {},
        )
    except Exception as exc:
        logger.warning("backup audit log failed (%s): %s", event_type, exc)


# ── Entitlement ───────────────────────────────────────────────────────────────

@dataclass
class BackupEntitlement:
    manual_backup_enabled: bool
    automatic_backup_enabled: bool
    max_manual_backups: int
    plan: str
    admin_override: bool = False


def get_backup_entitlement(user_id: int, admin_override: bool = False) -> BackupEntitlement:
    """Derive backup entitlement from the user's plan. admin_override bypasses all limits."""
    if admin_override:
        return BackupEntitlement(
            manual_backup_enabled=True,
            automatic_backup_enabled=True,
            max_manual_backups=99,
            plan="admin_override",
            admin_override=True,
        )
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT plan FROM users WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        plan = (row["plan"] if row else "free") or "free"
    finally:
        _rel(conn)

    return BackupEntitlement(
        manual_backup_enabled=plan in _MANUAL_PLANS,
        automatic_backup_enabled=plan in _AUTOMATIC_PLANS,
        max_manual_backups=_MAX_MANUAL.get(plan, 0),
        plan=plan,
    )


# ── SHA256 ────────────────────────────────────────────────────────────────────

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


# ── DB container env ──────────────────────────────────────────────────────────

def _get_db_env(db_container: str) -> dict:
    try:
        r = subprocess.run(
            ["docker", "inspect", "--format",
             "{{range .Config.Env}}{{.}}\n{{end}}", db_container],
            capture_output=True, text=True, timeout=10,
        )
        env: dict = {}
        for line in r.stdout.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
        return env
    except Exception:
        return {}


# ── File backup ───────────────────────────────────────────────────────────────

def _backup_files(container_name: str, work_dir: Path) -> dict:
    """
    Create files.tar.gz from /opt/clients/<container_name> on the host.
    Returns {"path": Path, "size_bytes": int, "sha256": str} or raises.
    """
    source = Path(_CLIENTS_DIR) / container_name
    if not source.is_dir():
        raise ValueError(f"backup_files_path_missing:{source}")

    dest = work_dir / "files.tar.gz"

    def _exclude(tarinfo: tarfile.TarInfo) -> Optional[tarfile.TarInfo]:
        name = Path(tarinfo.name).name
        if name in _EXCLUDE_NAMES:
            return None
        # Block symlinks that escape the source tree
        if tarinfo.issym() or tarinfo.islnk():
            try:
                link_target = Path(tarinfo.linkname)
                if not link_target.is_absolute():
                    link_target = (source / tarinfo.name).parent / link_target
                link_target.resolve().relative_to(source.resolve())
            except (ValueError, OSError):
                logger.warning("backup: skipping unsafe symlink %s", tarinfo.name)
                return None
        return tarinfo

    with tarfile.open(dest, "w:gz") as tar:
        tar.add(str(source), arcname=".", filter=_exclude)

    sha = _sha256_file(dest)
    return {"path": dest, "size_bytes": dest.stat().st_size, "sha256": sha}


# ── Database backup ───────────────────────────────────────────────────────────

def _backup_database(db_container_name: str, work_dir: Path) -> dict:
    """
    Dump MariaDB/MySQL via docker exec using credentials from container env.
    Password is never passed on the host command line — resolved inside the
    container's shell via $MYSQL_PASSWORD.
    Returns {"path": Path, "size_bytes": int, "sha256": str} or raises.
    """
    dest = work_dir / "database.sql.gz"

    r = subprocess.run(
        [
            "docker", "exec", db_container_name,
            "sh", "-c",
            # shellcheck: variables resolved inside container — not on host
            'mariadb-dump -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" 2>/dev/null | gzip'
            ' || mysqldump -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" 2>/dev/null | gzip',
        ],
        capture_output=True,
        timeout=180,
    )

    if r.returncode != 0 or len(r.stdout) < 20:
        stderr_safe = r.stderr.decode(errors="replace").replace(
            _get_db_env(db_container_name).get("MYSQL_PASSWORD", ""), "***"
        )[:200]
        raise ValueError(f"backup_database_dump_failed:{stderr_safe}")

    dest.write_bytes(r.stdout)
    sha = _sha256_file(dest)
    return {"path": dest, "size_bytes": dest.stat().st_size, "sha256": sha}


# ── Manifest ──────────────────────────────────────────────────────────────────

def _write_manifest(work_dir: Path, *, backup_id: str, hosting_id: int, subdomain: str,
                    container_name: str, db_container_name: Optional[str],
                    backup_type: str, trigger: str, storage_driver: str,
                    retention_policy: str, files_info: Optional[dict],
                    db_info: Optional[dict], db_skipped: bool,
                    db_skip_reason: str) -> dict:
    manifest = {
        "backup_id": backup_id,
        "hosting_id": hosting_id,
        "subdomain": subdomain,
        "container_name": container_name,
        "db_container_name": db_container_name,
        "backup_type": backup_type,
        "trigger": trigger,
        "storage_driver": storage_driver,
        "retention_policy": retention_policy,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": {
            "path": str(files_info["path"].name) if files_info else None,
            "size_bytes": files_info["size_bytes"] if files_info else 0,
            "sha256": files_info["sha256"] if files_info else None,
            "skipped": files_info is None,
        },
        "database": {
            "path": "database.sql.gz" if db_info else None,
            "size_bytes": db_info["size_bytes"] if db_info else 0,
            "sha256": db_info["sha256"] if db_info else None,
            "skipped": db_skipped,
            "skip_reason": db_skip_reason if db_skipped else None,
        },
        "schema_version": 1,
    }
    manifest_path = work_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    sha = _sha256_file(manifest_path)
    return {"path": manifest_path, "sha256": sha, "manifest": manifest}


# ── DB record helpers ─────────────────────────────────────────────────────────

def _insert_backup_record(hosting_id: int, user_id: int, backup_type: str,
                           trigger: str, retention_policy: str,
                           container_name: str, db_container_name: Optional[str],
                           subdomain: str, expires_at: Optional[datetime]) -> int:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO tenant_backups
               (hosting_id, user_id, backup_type, status, trigger,
                storage_driver, retention_policy, container_name,
                db_container_name, subdomain, started_at, expires_at)
               VALUES (%s,%s,%s,'running',%s,'local',%s,%s,%s,%s,NOW(),%s)
               RETURNING backup_id""",
            (hosting_id, user_id, backup_type, trigger, retention_policy,
             container_name, db_container_name, subdomain, expires_at),
        )
        row = cur.fetchone()
        conn.commit()
        return int(row["backup_id"])
    except Exception:
        conn.rollback()
        raise
    finally:
        _rel(conn)


def _update_backup_completed(backup_id: int, local_path: str,
                              files_path: Optional[str], database_path: Optional[str],
                              manifest_path: Optional[str],
                              files_size: int, db_size: int,
                              sha256_files: Optional[str], sha256_db: Optional[str],
                              sha256_manifest: Optional[str]) -> None:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """UPDATE tenant_backups SET
                status='completed', finished_at=NOW(),
                local_path=%s, files_path=%s, database_path=%s, manifest_path=%s,
                files_size_bytes=%s, database_size_bytes=%s,
                total_size_bytes=%s,
                sha256_files=%s, sha256_database=%s, sha256_manifest=%s
               WHERE backup_id=%s""",
            (local_path, files_path, database_path, manifest_path,
             files_size, db_size, files_size + db_size,
             sha256_files, sha256_db, sha256_manifest,
             backup_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _rel(conn)


def _update_backup_failed(backup_id: int, error_code: str, error_message: str) -> None:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """UPDATE tenant_backups SET status='failed', finished_at=NOW(),
               error_code=%s, error_message=%s WHERE backup_id=%s""",
            (error_code, error_message[:500], backup_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _rel(conn)


# ── Retention cleanup ─────────────────────────────────────────────────────────

def _cleanup_automatic_previous(hosting_id: int, new_backup_id: Optional[int]) -> int:
    """Delete all previous *completed* automatic backups for this tenant except new_backup_id.
    Protected backups and running/pending backups are always skipped."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        if new_backup_id is not None:
            cur.execute(
                """SELECT backup_id, local_path FROM tenant_backups
                   WHERE hosting_id=%s AND trigger='schedule' AND status='completed'
                     AND backup_id != %s AND (protected IS NULL OR protected = FALSE)""",
                (hosting_id, new_backup_id),
            )
        else:
            # Called from admin cleanup — keep the newest, delete the rest
            cur.execute(
                """SELECT backup_id, local_path FROM tenant_backups
                   WHERE hosting_id=%s AND trigger='schedule' AND status='completed'
                     AND (protected IS NULL OR protected = FALSE)
                   ORDER BY started_at DESC OFFSET 1""",
                (hosting_id,),
            )
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        _rel(conn)

    deleted = 0
    for row in rows:
        try:
            _delete_backup_files(row.get("local_path"))
            conn2 = _get_conn()
            try:
                c2 = conn2.cursor()
                c2.execute(
                    "UPDATE tenant_backups SET status='deleted' WHERE backup_id=%s",
                    (row["backup_id"],),
                )
                conn2.commit()
                deleted += 1
            finally:
                _rel(conn2)
        except Exception as exc:
            logger.warning("cleanup_automatic_previous: error on backup_id=%s: %s", row["backup_id"], exc)
    return deleted


def _cleanup_manual_excess(hosting_id: int, max_manual: int) -> int:
    """Keep only the newest max_manual completed manual backups; delete the rest.
    Protected backups are never deleted."""
    if max_manual <= 0:
        return 0
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT backup_id, local_path FROM tenant_backups
               WHERE hosting_id=%s AND trigger='manual' AND status='completed'
                 AND (protected IS NULL OR protected = FALSE)
               ORDER BY started_at DESC""",
            (hosting_id,),
        )
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        _rel(conn)

    to_delete = rows[max_manual:]
    deleted = 0
    for row in to_delete:
        try:
            _delete_backup_files(row.get("local_path"))
            conn2 = _get_conn()
            try:
                c2 = conn2.cursor()
                c2.execute(
                    "UPDATE tenant_backups SET status='deleted' WHERE backup_id=%s",
                    (row["backup_id"],),
                )
                conn2.commit()
                deleted += 1
            finally:
                _rel(conn2)
        except Exception as exc:
            logger.warning("cleanup_manual_excess: error on backup_id=%s: %s", row["backup_id"], exc)
    return deleted


def _cleanup_expired_ttl() -> int:
    """Delete all backups whose expires_at has passed. Returns count deleted."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT backup_id, local_path FROM tenant_backups
               WHERE expires_at IS NOT NULL AND expires_at < NOW()
                 AND status NOT IN ('deleted', 'running', 'pending')""",
        )
        expired = [dict(r) for r in cur.fetchall()]
    finally:
        _rel(conn)

    deleted = 0
    for row in expired:
        try:
            _delete_backup_files(row.get("local_path"))
            conn2 = _get_conn()
            try:
                c2 = conn2.cursor()
                c2.execute(
                    "UPDATE tenant_backups SET status='deleted' WHERE backup_id=%s",
                    (row["backup_id"],),
                )
                conn2.commit()
                deleted += 1
            finally:
                _rel(conn2)
        except Exception as exc:
            logger.warning("_cleanup_expired_ttl: error on backup_id=%s: %s", row["backup_id"], exc)
    return deleted


def _delete_backup_files(local_path: Optional[str]) -> None:
    if not local_path:
        return
    p = Path(local_path)
    # Safety: must be under BACKUP_LOCAL_DIR
    try:
        p.resolve().relative_to(_backup_local_dir().resolve())
    except ValueError:
        logger.warning("backup: refusing to delete out-of-tree path %s", local_path)
        return
    if p.is_dir():
        shutil.rmtree(p, ignore_errors=True)


# ── Main entry point ──────────────────────────────────────────────────────────

def create_tenant_backup(
    hosting_id: int,
    *,
    backup_type: str = "full",
    trigger: str = "manual",
    requested_by_user_id: Optional[int] = None,
    admin_override: bool = False,
) -> dict:
    """
    Create a local backup for a static tenant.

    Returns a result dict with keys:
      backup_id, status, trigger, files_size_bytes, database_size_bytes,
      total_size_bytes, sha256_files, sha256_database, error_code, error_message
    """
    if not _backup_enabled() and trigger not in _INTERNAL_TRIGGERS:
        return {"status": "skipped", "error_code": "backup_not_configured",
                "error_message": "BACKUP_ENABLED=false"}

    # ── Fetch hosting ────────────────────────────────────────────────────────
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT hosting_id, user_id, name, subdomain, container_name, "
            "db_container_name, status FROM hostings WHERE hosting_id=%s",
            (hosting_id,),
        )
        row = cur.fetchone()
        hosting = dict(row) if row else None
    finally:
        _rel(conn)

    if not hosting:
        return {"status": "failed", "error_code": "backup_not_found",
                "error_message": f"hosting_id {hosting_id} not found"}

    user_id = hosting["user_id"]
    container_name = hosting["container_name"]
    db_container_name = hosting.get("db_container_name")
    subdomain = hosting.get("subdomain", "")

    # ── Entitlement check ────────────────────────────────────────────────────
    if trigger not in _INTERNAL_TRIGGERS:
        ent = get_backup_entitlement(user_id, admin_override=admin_override)
        if trigger == "schedule" and not ent.automatic_backup_enabled:
            _audit("backup.skipped_no_entitlement", hosting_id=hosting_id, user_id=user_id,
                   metadata={"plan": ent.plan, "trigger": trigger})
            logger.debug("backup: skipped (no entitlement) hosting_id=%d plan=%s", hosting_id, ent.plan)
            return {"status": "skipped", "error_code": "backup_plan_required",
                    "error_message": "automatic_backup_enabled=false for this plan"}
        if trigger == "manual" and not ent.manual_backup_enabled:
            _audit("backup.manual_denied_plan_required", hosting_id=hosting_id, user_id=user_id,
                   metadata={"plan": ent.plan})
            return {"status": "denied", "error_code": "backup_plan_required",
                    "error_message": "Los backups no están incluidos en tu plan.",
                    "upgrade_required": True,
                    "recommended_plan": "agencia_pro",
                    "addon": "daily_backups",
                    "plan": ent.plan}
    else:
        ent = BackupEntitlement(
            manual_backup_enabled=True, automatic_backup_enabled=True,
            max_manual_backups=99, plan="internal",
        )

    # ── Lock: no duplicate running backup for same hosting ───────────────────
    conn2 = _get_conn()
    try:
        cur2 = conn2.cursor()
        cur2.execute(
            "SELECT backup_id FROM tenant_backups "
            "WHERE hosting_id=%s AND status IN ('pending','running') LIMIT 1",
            (hosting_id,),
        )
        running = cur2.fetchone()
    finally:
        _rel(conn2)

    if running:
        return {"status": "skipped", "error_code": "backup_already_running",
                "error_message": f"backup_id={running['backup_id']} already running"}

    # ── Determine retention policy + expiry ──────────────────────────────────
    if trigger == "schedule":
        retention_policy = "latest_only"
        expires_at = None
    elif trigger in _INTERNAL_TRIGGERS:
        retention_policy = "ttl"
        expires_at = datetime.now(timezone.utc) + timedelta(hours=_pre_restore_ttl_hours())
    else:
        retention_policy = "manual_limited"
        expires_at = None

    # ── Insert pending record ────────────────────────────────────────────────
    backup_id_int = _insert_backup_record(
        hosting_id, user_id, backup_type, trigger, retention_policy,
        container_name, db_container_name, subdomain, expires_at,
    )
    backup_id = str(backup_id_int)

    _audit("backup.tenant.started", hosting_id=hosting_id, user_id=requested_by_user_id or user_id,
           metadata={"backup_id": backup_id, "backup_type": backup_type, "trigger": trigger})

    # ── Determine backup sub-dir ─────────────────────────────────────────────
    if trigger == "schedule":
        sub_dir = "automatic"
    elif trigger in _INTERNAL_TRIGGERS:
        sub_dir = "internal"
    else:
        sub_dir = "manual"

    final_dir = _backup_local_dir() / "tenants" / str(hosting_id) / sub_dir / backup_id
    work_dir = Path(tempfile.mkdtemp(prefix=f"hg_backup_{backup_id}_"))

    files_info: Optional[dict] = None
    db_info: Optional[dict] = None
    db_skipped = False
    db_skip_reason = ""
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    try:
        # ── Files backup ─────────────────────────────────────────────────────
        if backup_type in ("full", "files"):
            if not os.getenv("BACKUP_FILES_ENABLED", "true").lower() == "false":
                try:
                    files_info = _backup_files(container_name, work_dir)
                    _audit("backup.tenant.files_completed", hosting_id=hosting_id,
                           user_id=user_id,
                           metadata={"backup_id": backup_id,
                                     "size_bytes": files_info["size_bytes"]})
                except ValueError as exc:
                    msg = str(exc)
                    if msg.startswith("backup_files_path_missing:"):
                        error_code = "backup_files_path_missing"
                        error_message = msg
                        raise
                    raise

        # ── Database backup ──────────────────────────────────────────────────
        if backup_type in ("full", "database"):
            if not db_container_name:
                if backup_type == "database":
                    error_code = "backup_database_container_missing"
                    error_message = "db_container_name is not set for this hosting"
                    raise ValueError(error_message)
                db_skipped = True
                db_skip_reason = "no_database_container"
            else:
                if not os.getenv("BACKUP_DATABASE_ENABLED", "true").lower() == "false":
                    try:
                        db_info = _backup_database(db_container_name, work_dir)
                        _audit("backup.tenant.database_completed", hosting_id=hosting_id,
                               user_id=user_id,
                               metadata={"backup_id": backup_id,
                                         "size_bytes": db_info["size_bytes"]})
                    except ValueError as exc:
                        msg = str(exc)
                        if backup_type == "full":
                            # files already done — log warning but don't fail the whole backup
                            logger.warning("backup: db dump failed for hosting_id=%d: %s", hosting_id, msg)
                            db_skipped = True
                            db_skip_reason = "dump_failed"
                        else:
                            error_code = "backup_database_dump_failed"
                            error_message = msg
                            raise

        # ── Manifest ─────────────────────────────────────────────────────────
        manifest_result = _write_manifest(
            work_dir,
            backup_id=backup_id,
            hosting_id=hosting_id,
            subdomain=subdomain,
            container_name=container_name,
            db_container_name=db_container_name,
            backup_type=backup_type,
            trigger=trigger,
            storage_driver="local",
            retention_policy=retention_policy,
            files_info=files_info,
            db_info=db_info,
            db_skipped=db_skipped,
            db_skip_reason=db_skip_reason,
        )

        # ── Move to final dir (atomic) ────────────────────────────────────────
        final_dir.mkdir(parents=True, exist_ok=True)
        if files_info:
            shutil.move(str(files_info["path"]), str(final_dir / "files.tar.gz"))
            files_info["path"] = final_dir / "files.tar.gz"
        if db_info:
            shutil.move(str(db_info["path"]), str(final_dir / "database.sql.gz"))
            db_info["path"] = final_dir / "database.sql.gz"
        shutil.move(str(manifest_result["path"]), str(final_dir / "manifest.json"))
        manifest_result["path"] = final_dir / "manifest.json"

        # ── Persist completed record ──────────────────────────────────────────
        _update_backup_completed(
            backup_id=backup_id_int,
            local_path=str(final_dir),
            files_path=str(files_info["path"]) if files_info else None,
            database_path=str(db_info["path"]) if db_info else None,
            manifest_path=str(manifest_result["path"]),
            files_size=files_info["size_bytes"] if files_info else 0,
            db_size=db_info["size_bytes"] if db_info else 0,
            sha256_files=files_info["sha256"] if files_info else None,
            sha256_db=db_info["sha256"] if db_info else None,
            sha256_manifest=manifest_result["sha256"],
        )

        _audit("backup.tenant.completed", hosting_id=hosting_id,
               user_id=requested_by_user_id or user_id,
               metadata={"backup_id": backup_id, "backup_type": backup_type,
                         "trigger": trigger,
                         "total_size_bytes": (files_info["size_bytes"] if files_info else 0)
                                             + (db_info["size_bytes"] if db_info else 0)})

        # ── Retention cleanup ─────────────────────────────────────────────────
        if trigger == "schedule":
            deleted = _cleanup_automatic_previous(hosting_id, backup_id_int)
            if deleted:
                logger.info("backup: cleaned up %d old automatic backup(s) for hosting_id=%d",
                            deleted, hosting_id)
        elif trigger == "manual":
            max_m = ent.max_manual_backups if not admin_override else _max_manual()
            _cleanup_manual_excess(hosting_id, max_m)

        result = {
            "backup_id": backup_id_int,
            "status": "completed",
            "trigger": trigger,
            "backup_type": backup_type,
            "local_path": str(final_dir),
            "files_size_bytes": files_info["size_bytes"] if files_info else 0,
            "database_size_bytes": db_info["size_bytes"] if db_info else 0,
            "total_size_bytes": (files_info["size_bytes"] if files_info else 0)
                                + (db_info["size_bytes"] if db_info else 0),
            "sha256_files": files_info["sha256"] if files_info else None,
            "sha256_database": db_info["sha256"] if db_info else None,
            "database_skipped": db_skipped,
            "database_skip_reason": db_skip_reason,
            "error_code": None,
            "error_message": None,
        }
        return result

    except Exception as exc:
        msg = str(exc)
        if not error_code:
            error_code = "backup_failed"
        if not error_message:
            error_message = msg[:500]
        _update_backup_failed(backup_id_int, error_code, error_message)
        _audit("backup.tenant.failed", hosting_id=hosting_id,
               user_id=requested_by_user_id or user_id,
               metadata={"backup_id": backup_id, "error_code": error_code,
                         "error_message": error_message})
        logger.error("backup: failed hosting_id=%d backup_id=%s: %s", hosting_id, backup_id, msg)
        # Clean up work dir on failure — final_dir may be partial
        try:
            if final_dir.exists():
                shutil.rmtree(final_dir, ignore_errors=True)
        except Exception:
            pass
        return {"backup_id": backup_id_int, "status": "failed",
                "error_code": error_code, "error_message": error_message}
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# ── List / get / delete ───────────────────────────────────────────────────────

def list_tenant_backups(hosting_id: int, user_id: Optional[int] = None,
                        admin: bool = False, limit: int = 20) -> list:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        if admin:
            cur.execute(
                """SELECT backup_id, hosting_id, user_id, backup_type, status, trigger,
                          retention_policy, files_size_bytes, database_size_bytes,
                          total_size_bytes, subdomain, container_name,
                          started_at, finished_at, expires_at, error_code, error_message
                   FROM tenant_backups WHERE hosting_id=%s AND status != 'deleted'
                   ORDER BY started_at DESC LIMIT %s""",
                (hosting_id, limit),
            )
        else:
            cur.execute(
                """SELECT backup_id, hosting_id, user_id, backup_type, status, trigger,
                          retention_policy, files_size_bytes, database_size_bytes,
                          total_size_bytes, subdomain, container_name,
                          started_at, finished_at, expires_at, error_code, error_message
                   FROM tenant_backups WHERE hosting_id=%s AND user_id=%s AND status != 'deleted'
                   ORDER BY started_at DESC LIMIT %s""",
                (hosting_id, user_id, limit),
            )
        return [dict(r) for r in cur.fetchall()]
    finally:
        _rel(conn)


def get_tenant_backup(backup_id: int, user_id: Optional[int] = None,
                      admin: bool = False) -> Optional[dict]:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        if admin:
            cur.execute("SELECT * FROM tenant_backups WHERE backup_id=%s", (backup_id,))
        else:
            cur.execute(
                "SELECT * FROM tenant_backups WHERE backup_id=%s AND user_id=%s",
                (backup_id, user_id),
            )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        _rel(conn)


def delete_tenant_backup(backup_id: int, user_id: Optional[int] = None,
                         admin: bool = False) -> bool | str:
    """
    Returns True on success, False if not found, 'protected' if backup is protected.
    Protected backups can only be deleted by removing the protection first.
    """
    conn = _get_conn()
    try:
        cur = conn.cursor()
        if admin:
            cur.execute("SELECT * FROM tenant_backups WHERE backup_id=%s", (backup_id,))
        else:
            cur.execute(
                "SELECT * FROM tenant_backups WHERE backup_id=%s AND user_id=%s",
                (backup_id, user_id),
            )
        row = cur.fetchone()
        if not row:
            return False
        backup = dict(row)
        if backup.get("protected"):
            return "protected"
        _delete_backup_files(backup.get("local_path"))
        cur.execute(
            "UPDATE tenant_backups SET status='deleted', finished_at=NOW() WHERE backup_id=%s",
            (backup_id,),
        )
        conn.commit()
        _audit("backup.tenant.deleted",
               hosting_id=backup.get("hosting_id"),
               user_id=backup.get("user_id"),
               metadata={"backup_id": str(backup_id), "trigger": backup.get("trigger")})
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        _rel(conn)


# ── Scheduler job ─────────────────────────────────────────────────────────────

def backup_tenants_job() -> None:
    """
    Daily job: create automatic backups for tenants with automatic_backup_enabled.
    Respects entitlement — does NOT backup all active tenants.
    Staggers start using hash(hosting_id) % stagger_window but runs synchronously
    within the scheduler's thread (schedule_job dispatches to executor).
    """
    if not _backup_enabled():
        logger.info("backup_tenants_job: BACKUP_ENABLED=false, skipping")
        return

    from app.infra.db import reset_pg_connection
    reset_pg_connection()

    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT h.hosting_id, h.user_id, h.container_name,
                      h.db_container_name, h.subdomain, h.status, u.plan
               FROM hostings h
               JOIN users u ON u.user_id = h.user_id
               WHERE h.status IN ('active', 'active_with_placeholder')
                 AND h.container_name IS NOT NULL AND h.container_name != ''""",
        )
        candidates = [dict(r) for r in cur.fetchall()]
    finally:
        _rel(conn)

    eligible = []
    for c in candidates:
        hosting_id = c["hosting_id"]
        plan = c.get("plan") or "free"
        try:
            from app.services.backup_policy_service import get_effective_policy
            policy = get_effective_policy(hosting_id)
            if policy.paused:
                logger.debug("backup_tenants_job: skipped paused hosting_id=%d", hosting_id)
                continue
            if not policy.automatic_backup_enabled:
                logger.debug("backup_tenants_job: skipped no_entitlement hosting_id=%d plan=%s",
                             hosting_id, plan)
                continue
            eligible.append(c)
        except Exception as exc:
            # Policy lookup failure → fall back to plan-based check
            if plan in _AUTOMATIC_PLANS:
                eligible.append(c)
            else:
                logger.debug("backup_tenants_job: policy error hosting_id=%d: %s", hosting_id, exc)

    logger.info("backup_tenants_job: %d eligible tenants (of %d active)",
                len(eligible), len(candidates))

    for hosting in eligible:
        hosting_id = hosting["hosting_id"]
        try:
            result = create_tenant_backup(
                hosting_id,
                backup_type="full",
                trigger="schedule",
            )
            status = result.get("status")
            if status == "completed":
                logger.info("backup_tenants_job: completed hosting_id=%d size=%s",
                            hosting_id, result.get("total_size_bytes"))
            elif status == "skipped":
                logger.debug("backup_tenants_job: skipped hosting_id=%d reason=%s",
                             hosting_id, result.get("error_code"))
            else:
                logger.warning("backup_tenants_job: failed hosting_id=%d code=%s msg=%s",
                               hosting_id, result.get("error_code"), result.get("error_message"))
        except Exception as exc:
            logger.error("backup_tenants_job: exception hosting_id=%d: %s", hosting_id, exc)


# ── Full retention cleanup (scheduled) ───────────────────────────────────────

def cleanup_backup_retention() -> dict:
    """
    Periodic cleanup:
      1. Mark expired TTL backups as deleted + remove files
      2. For automatic/latest_only: remove old automatic if a newer completed exists
      3. Enforce manual max per tenant
    """
    from app.infra.db import reset_pg_connection
    reset_pg_connection()

    deleted_ttl = deleted_auto = deleted_manual = errors = 0

    # 1. Expired TTL (internal)
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT backup_id, local_path FROM tenant_backups
               WHERE expires_at IS NOT NULL AND expires_at < NOW()
                 AND status NOT IN ('deleted', 'running', 'pending')""",
        )
        expired = [dict(r) for r in cur.fetchall()]
    finally:
        _rel(conn)

    for row in expired:
        try:
            _delete_backup_files(row.get("local_path"))
            conn2 = _get_conn()
            try:
                c2 = conn2.cursor()
                c2.execute(
                    "UPDATE tenant_backups SET status='deleted' WHERE backup_id=%s",
                    (row["backup_id"],),
                )
                conn2.commit()
                deleted_ttl += 1
            finally:
                _rel(conn2)
        except Exception as exc:
            logger.warning("cleanup_retention: TTL error on backup_id=%s: %s", row["backup_id"], exc)
            errors += 1

    # 2. Automatic latest_only: get all hosting_ids with multiple completed automatic backups
    conn3 = _get_conn()
    try:
        cur3 = conn3.cursor()
        cur3.execute(
            """SELECT DISTINCT hosting_id FROM tenant_backups
               WHERE trigger='schedule' AND status='completed'
               GROUP BY hosting_id HAVING COUNT(*) > 1""",
        )
        multi = [r["hosting_id"] for r in cur3.fetchall()]
    finally:
        _rel(conn3)

    for hid in multi:
        conn4 = _get_conn()
        try:
            c4 = conn4.cursor()
            c4.execute(
                """SELECT backup_id FROM tenant_backups
                   WHERE hosting_id=%s AND trigger='schedule' AND status='completed'
                   ORDER BY started_at DESC""",
                (hid,),
            )
            bids = [r["backup_id"] for r in c4.fetchall()]
        finally:
            _rel(conn4)
        # Keep newest, delete the rest
        if len(bids) > 1:
            n = _cleanup_automatic_previous(hid, bids[0])
            deleted_auto += n

    # 3. Manual excess per tenant
    conn5 = _get_conn()
    try:
        c5 = conn5.cursor()
        c5.execute(
            """SELECT DISTINCT hosting_id FROM tenant_backups
               WHERE trigger='manual' AND status='completed'""",
        )
        manual_hostings = [r["hosting_id"] for r in c5.fetchall()]
    finally:
        _rel(conn5)

    max_m = _max_manual()
    for hid in manual_hostings:
        n = _cleanup_manual_excess(hid, max_m)
        deleted_manual += n

    result = {
        "deleted_ttl": deleted_ttl,
        "deleted_automatic": deleted_auto,
        "deleted_manual": deleted_manual,
        "errors": errors,
    }
    logger.info("cleanup_backup_retention: %s", result)
    _audit("backup.retention.cleanup_completed", metadata=result)
    return result
