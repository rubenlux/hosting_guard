"""
AI Eyes Layer — Incident Feed Bridge (entrypoint)

Syncs open alerts from detection tables into system_incidents.
Implementation lives in app/services/incidents/.

Backward-compat aliases (_sync_*, _GENERIC_DEPLOY_CODES) kept so
existing callers don't break.
"""
import logging

from app.services.incidents.sync_security_events import sync_security_events
from app.services.incidents.sync_site_alerts import sync_site_alerts
from app.services.incidents.sync_system_alerts import sync_system_alerts
from app.services.incidents.sync_deploy_events import (
    sync_deploy_events,
    _GENERIC_DEPLOY_CODES,
    _repo_hash,
)

logger = logging.getLogger(__name__)

# Backward-compat aliases used by tests and external callers
_sync_security_events = sync_security_events
_sync_site_alerts     = sync_site_alerts
_sync_system_alerts   = sync_system_alerts
_sync_deploy_events   = sync_deploy_events


def sync_incidents_feed() -> None:
    """Called by scheduler every 120 s. Syncs all sources into system_incidents."""
    from app.infra.db import get_connection, release_connection

    conn = None
    try:
        conn = get_connection()
        totals: dict = {"created": 0, "updated": 0, "resolved": 0}

        for label, fn in (
            ("security_events", sync_security_events),
            ("site_alerts",     sync_site_alerts),
            ("system_alerts",   sync_system_alerts),
            ("deploy_events",   sync_deploy_events),
        ):
            try:
                counts = fn(conn)
                conn.commit()
                for k in totals:
                    totals[k] += counts.get(k, 0)
                logger.debug("sync_incidents_feed[%s]: %s", label, counts)
            except Exception as exc:
                conn.rollback()
                logger.error(
                    "sync_incidents_feed[%s] failed: %s", label, exc, exc_info=True
                )

        if any(totals.values()):
            logger.info(
                "sync_incidents_feed: created=%d updated=%d resolved=%d",
                totals["created"], totals["updated"], totals["resolved"],
            )

    except Exception as exc:
        logger.exception("sync_incidents_feed: unexpected error: %s", exc)
    finally:
        if conn:
            release_connection(conn)
