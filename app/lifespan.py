"""
FastAPI lifespan context manager.

Extracted from main.py so startup/shutdown logic lives in one place and
main.py stays focused on route registration and middleware configuration.
"""
import logging
import os
from contextlib import asynccontextmanager

from app.services.expiration_job import check_and_expire_free_hostings
from app.services.traffic_collector import collect_traffic
from app.services.health_checker import check_all_hostings
from app.services.reconciler import reconcile_containers
from app.services.scheduler import schedule_job
from app.services.prometheus_alert_poller import poll_prometheus_alerts
from app.services.ssl_checker import check_ssl_for_all_hostings
from app.services.backup_service import auto_backup_all
from app.api.config import ENABLE_CAPACITY_FORECAST
from app.infra.arq_pool import init_arq_pool, close_arq_pool

logger = logging.getLogger("hosting_guard_audit")

# RUN_ORCHESTRATOR=false → background schedulers disabled.
# Set this when the dedicated orchestrator container is running to avoid double execution.
_RUN_ORCHESTRATOR = os.getenv("RUN_ORCHESTRATOR", "true").lower() != "false"


@asynccontextmanager
async def lifespan(app):
    # Initialize database schema (idempotent)
    from app.infra.migrations import init_db
    init_db()

    await init_arq_pool()

    if _RUN_ORCHESTRATOR:
        schedule_job(check_and_expire_free_hostings, interval=43200)  # 12 hours
        schedule_job(collect_traffic,                interval=300)     # 5 minutes
        schedule_job(check_all_hostings,             interval=300)     # 5 minutes
        schedule_job(reconcile_containers,           interval=300)     # 5 minutes
        schedule_job(poll_prometheus_alerts,         interval=60)      # 1 minute
        schedule_job(check_ssl_for_all_hostings,     interval=86400)   # daily
        schedule_job(auto_backup_all,                interval=86400)   # daily

        if ENABLE_CAPACITY_FORECAST:
            def _run_capacity_forecast():
                try:
                    from app.services.capacity_planner import evaluate_capacity_forecast
                    evaluate_capacity_forecast()
                except Exception as exc:
                    logger.warning("capacity_forecast job failed: %s", exc)

            schedule_job(_run_capacity_forecast, interval=600)        # 10 minutes
            logger.info("lifespan: 8 background jobs scheduled (capacity forecast enabled)")
        else:
            logger.info("lifespan: 7 background jobs scheduled")
    else:
        logger.info("lifespan: RUN_ORCHESTRATOR=false — background tasks disabled (orchestrator container active)")

    yield

    await close_arq_pool()
    # Shutdown: asyncio cancels running tasks automatically on event loop close.
