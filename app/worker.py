"""
Arq background worker — runs long-lived import jobs outside the HTTP process.

Start with:
    arq app.worker.WorkerSettings

Docker-compose starts this as the `worker` service.

Why Arq instead of run_in_executor?
  - Jobs survive app restarts (state stored in Redis queue).
  - Worker is isolated from HTTP concurrency (no shared thread pool).
  - Orphaned jobs (in-progress at restart) are auto-recovered on startup.
"""
import asyncio
import logging
import os
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

_REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
_ARQ_QUEUE = "arq:hg"


def _redis_settings():
    from arq.connections import RedisSettings
    p = urllib.parse.urlparse(_REDIS_URL)
    return RedisSettings(
        host=p.hostname or "redis",
        port=p.port or 6379,
        password=p.password or None,
    )


# ── Job functions ─────────────────────────────────────────────────────────────

async def import_site_job(
    ctx: dict,
    job_id: int,
    hosting_id: int,
    user_id: int,
    file_path: str,
    sql_path: Optional[str] = None,
):
    """Execute the WordPress import pipeline in a thread (blocking I/O)."""
    from pathlib import Path
    from app.api.routes.import_hosting import _run_pipeline

    loop = asyncio.get_running_loop()
    dest = Path(file_path)
    sql  = Path(sql_path) if sql_path else None

    logger.info("[arq] import_site_job start: job_id=%d hosting_id=%d", job_id, hosting_id)
    await loop.run_in_executor(None, _run_pipeline, job_id, hosting_id, user_id, dest, sql)
    logger.info("[arq] import_site_job done:  job_id=%d", job_id)


# ── Lifecycle hooks ───────────────────────────────────────────────────────────

async def startup(ctx: dict):
    from app.infra.db import init_db_pool
    init_db_pool(minconn=1, maxconn=10)

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _mark_orphaned_jobs)
    logger.info("Arq worker ready")


def _mark_orphaned_jobs() -> None:
    """Mark jobs stuck in a non-terminal state for >30 min as failed.

    Called once on worker startup. A job in 'processing' / 'restoring_files' /
    etc. that is >30 min old was almost certainly left behind by a previous
    worker crash — it will never complete on its own.
    """
    from app.infra.db import get_connection, release_connection

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cutoff     = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        now_str    = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """
            UPDATE import_jobs
               SET status     = 'failed',
                   error      = 'Job orphaned — worker restarted',
                   updated_at = %s
             WHERE status NOT IN ('completed', 'failed')
               AND updated_at < %s
            """,
            (now_str, cutoff),
        )
        n = cursor.rowcount
        conn.commit()
        if n:
            logger.warning("[arq] startup: marked %d orphaned job(s) as failed", n)
    except Exception as exc:
        logger.error("[arq] startup: orphan cleanup failed: %s", exc)
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        release_connection(conn)


async def shutdown(ctx: dict):
    logger.info("Arq worker shut down")


# ── Worker settings ───────────────────────────────────────────────────────────

class WorkerSettings:
    functions      = [import_site_job]
    on_startup     = startup
    on_shutdown    = shutdown
    redis_settings = _redis_settings()
    queue_name     = _ARQ_QUEUE
    max_jobs       = 4        # up to 4 concurrent import pipelines
    job_timeout    = 3600     # 1 h max per job (large sites can take ~10 min)
    keep_result    = 86400    # keep result in Redis for 24 h
