"""
Zombie container reconciler.

Runs every 5 minutes. Compares containers marked 'running' in the DB against
the live output of `docker ps`. Containers missing from Docker are logged as
zombies and their DB status updated to 'zombie' so the dashboard reflects
reality and operators can investigate.

A "zombie" is a container that the DB believes is running but Docker has no
record of — typically caused by a failed deploy, an external `docker rm`, or
a host restart that wiped containers without updating the DB.
"""
import asyncio
import logging

logger = logging.getLogger(__name__)


async def reconcile_containers() -> None:
    """One reconciliation pass — safe to call from the scheduler loop."""
    from app.infra.audit.hosting_repository import HostingRepository
    from app.infra.docker_client import run_docker_command_async

    hosting_repo = HostingRepository()

    # 1. Fetch all DB containers that we believe are running.
    try:
        db_running = hosting_repo.get_all_running()  # list of dicts with container_name + hosting_id
    except Exception:
        logger.exception("reconciler: failed to query DB running containers")
        return

    if not db_running:
        return

    # 2. Ask Docker for the live set of container names.
    try:
        code, stdout, stderr = await run_docker_command_async(
            ["ps", "--format", "{{.Names}}"],
            timeout=15,
        )
        if code != 0:
            logger.error("reconciler: docker ps exited %d: %s — skipping this pass", code, stderr)
            return
        docker_names: set[str] = {name.strip() for name in stdout.splitlines() if name.strip()}
    except Exception:
        logger.exception("reconciler: docker ps failed — skipping this pass")
        return

    # 3. Find DB entries whose container is missing from Docker.
    zombies = [h for h in db_running if h["container_name"] not in docker_names]

    if not zombies:
        logger.debug("reconciler: no zombies found (%d running containers checked)", len(db_running))
        return

    # 4. Update their status in the DB and log for the operator.
    for zombie in zombies:
        try:
            hosting_repo.update_status(zombie["hosting_id"], "zombie")
            logger.warning(
                "reconciler: zombie detected — hosting_id=%s container=%s "
                "was 'running' in DB but not found in docker ps",
                zombie["hosting_id"],
                zombie["container_name"],
            )
        except Exception:
            logger.exception(
                "reconciler: failed to update status for hosting_id=%s",
                zombie["hosting_id"],
            )
