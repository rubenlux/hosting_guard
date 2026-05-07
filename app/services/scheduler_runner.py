"""
Standalone scheduler runner.

Executes all periodic background jobs:
  - orchestrator     (throttle / autoscale / restart)        10 s
  - poll_prometheus  (alert polling)                          1 min
  - health_checker   (health score + DB alerts)               5 min
  - traffic_collector                                         5 min
  - reconcile_containers (exited/zombie recovery)             5 min
  - expiration_job   (free plan suspension + cleanup)        12 h
  - ssl_checker      (cert expiry warnings)                  24 h
  - auto_backup_all  (MariaDB + files backup)                24 h
  - cleanup_old_events (prune orchestrator_events table)     24 h
  - daily_report     (AI admin report at 08:00 UTC)           1 h check
  - detect_security   (attack detection, 10 rules)           60 s
  - cleanup_sessions  (expire/prune session rows)            24 h
  - check_pending_domains (DNS verify for custom domains)     5 min
  - capacity_forecast (optional, env-gated)                  10 min

Designed to run as a SINGLE instance in docker-compose so jobs are never
duplicated across Uvicorn workers.

Run as:
    python -m app.services.scheduler_runner

The app container runs with RUN_ORCHESTRATOR=false — no schedulers there.
This service runs with RUN_ORCHESTRATOR=true (implicit, it's always true here).

Shutdown: handles SIGTERM and SIGINT cleanly via asyncio signal handlers.
"""
import asyncio
import logging
import signal
import sys

from app.infra.logging_config import setup_logging

setup_logging()
logger = logging.getLogger("scheduler_runner")


def _cleanup_old_events() -> None:
    """Delete orchestrator_events older than 30 days."""
    from app.infra.db import get_connection, release_connection
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM orchestrator_events WHERE created_at < NOW() - INTERVAL '30 days'"
        )
        deleted = cur.rowcount
        conn.commit()
        if deleted:
            logger.info("cleanup_old_events: deleted %d rows", deleted)
    except Exception as exc:
        logger.warning("cleanup_old_events failed: %s", exc)
    finally:
        if conn:
            release_connection(conn)


async def _main() -> None:
    # ── DB pool (small — schedulers don't need many connections) ──────────────
    from app.infra.db import init_db_pool
    init_db_pool(minconn=1, maxconn=10)

    # ── Schema init (idempotent) ───────────────────────────────────────────────
    from app.infra.migrations import init_db
    init_db()

    logger.info("scheduler service started")

    # ── Register periodic jobs ────────────────────────────────────────────────
    from app.services.expiration_job import check_and_expire_free_hostings
    from app.services.traffic_collector import collect_traffic
    from app.services.health_checker import check_all_hostings
    from app.services.reconciler import reconcile_containers
    from app.services.scheduler import schedule_job
    from app.services.prometheus_alert_poller import poll_prometheus_alerts
    from app.services.ssl_checker import check_ssl_for_all_hostings
    from app.services.backup_service import auto_backup_all, cleanup_stale_backups
    from app.infra.audit.session_repository import cleanup_sessions
    from app.services.detect_security_anomalies import detect_security_anomalies
    from app.services.collect_resource_usage import collect_resource_usage
    from app.services.domain_checker import check_pending_domains
    from app.api.config import ENABLE_CAPACITY_FORECAST

    # Single pass of the intelligent orchestrator (throttle / autoscale / restart).
    # The orchestrator.py module exposes get_container_stats() + handle_container()
    # but its run_orchestrator() is a blocking loop — we call one iteration here so
    # schedule_job controls the interval instead.
    def _orchestrator_pass() -> None:
        try:
            from app.services.orchestrator import get_container_stats, handle_container
            for c in get_container_stats():
                handle_container(c)
        except Exception as exc:
            logger.warning("orchestrator_pass failed: %s", exc)

    def _daily_report_job() -> None:
        from datetime import datetime, timezone
        if datetime.now(timezone.utc).hour != 8:
            return
        from app.services.admin_ai_reporter import run_daily_report
        run_daily_report()

    # ── Hot path — resource management (10 s) ────────────────────────────────
    schedule_job(_orchestrator_pass,             interval=10)      # throttle / autoscale / restart
    # ── Sub-minute ───────────────────────────────────────────────────────────
    schedule_job(detect_security_anomalies,      interval=60)      # 60 s — attack detection
    schedule_job(poll_prometheus_alerts,         interval=60)      # 1 min
    schedule_job(collect_resource_usage,         interval=60)      # 60 s — CPU/RAM per container
    # ── Every 5 minutes ──────────────────────────────────────────────────────
    schedule_job(collect_traffic,                interval=300)     # 5 min
    schedule_job(check_all_hostings,             interval=300)     # 5 min
    schedule_job(reconcile_containers,           interval=300)     # 5 min
    schedule_job(check_pending_domains,          interval=300)     # 5 min
    # ── Every 12 hours ───────────────────────────────────────────────────────
    schedule_job(check_and_expire_free_hostings, interval=43200)   # 12 h
    # ── Daily ────────────────────────────────────────────────────────────────
    schedule_job(check_ssl_for_all_hostings,     interval=86400)   # 24 h
    schedule_job(auto_backup_all,                interval=86400)   # 24 h
    schedule_job(_cleanup_old_events,            interval=86400)   # 24 h
    schedule_job(cleanup_stale_backups,          interval=604800)  # 7 days
    schedule_job(cleanup_sessions,               interval=86400)   # 24 h
    schedule_job(_daily_report_job,              interval=3600)    # hourly check → fires at 8 AM UTC

    base_count = 15
    if ENABLE_CAPACITY_FORECAST:
        def _run_capacity_forecast():
            try:
                from app.services.capacity_planner import evaluate_capacity_forecast
                evaluate_capacity_forecast()
            except Exception as exc:
                logger.warning("capacity_forecast job failed: %s", exc)

        schedule_job(_run_capacity_forecast, interval=600)         # 10 min
        logger.info("scheduler: %d background jobs scheduled (capacity forecast enabled)", base_count + 1)
    else:
        logger.info("scheduler: %d background jobs scheduled", base_count)

    # ── Wait for shutdown signal ──────────────────────────────────────────────
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    logger.info("scheduler: running — send SIGTERM to stop")
    await stop.wait()
    logger.info("scheduler: shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass
    sys.exit(0)
