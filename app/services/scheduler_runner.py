"""
Standalone scheduler runner.

Executes all periodic background jobs (health_checker, traffic_collector,
expiration_job, reconcile_containers, poll_prometheus_alerts, capacity_forecast).

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
    from app.api.config import ENABLE_CAPACITY_FORECAST

    schedule_job(check_and_expire_free_hostings, interval=43200)  # 12 h
    schedule_job(collect_traffic,                interval=300)     # 5 min
    schedule_job(check_all_hostings,             interval=300)     # 5 min
    schedule_job(reconcile_containers,           interval=300)     # 5 min
    schedule_job(poll_prometheus_alerts,         interval=60)      # 1 min
    schedule_job(_cleanup_old_events,            interval=86400)   # 24 h

    if ENABLE_CAPACITY_FORECAST:
        def _run_capacity_forecast():
            try:
                from app.services.capacity_planner import evaluate_capacity_forecast
                evaluate_capacity_forecast()
            except Exception as exc:
                logger.warning("capacity_forecast job failed: %s", exc)

        schedule_job(_run_capacity_forecast, interval=600)         # 10 min
        logger.info("scheduler: 6 background jobs scheduled (capacity forecast enabled)")
    else:
        logger.info("scheduler: 5 background jobs scheduled")

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
