"""
Zombie + Exited container reconciler.

Runs every 5 minutes. Compares containers marked 'running' in the DB against
the live output of `docker ps -a`. Two failure modes are handled:

  - Exited: container exists but crashed/stopped. Attempt `docker start` to
    recover. If the restart succeeds the hosting stays 'running'; on failure
    it is marked 'failed' so operators know manual investigation is needed.

  - Zombie: container is completely absent from Docker (external `docker rm`,
    lost volume, etc.). Marked 'zombie' — human action required.

With `--restart unless-stopped` on all new containers, Docker auto-recovers
most crashes before this reconciler fires. This pass catches the remainder:
containers created before the policy was set, or repeated-crash loops where
Docker gave up restarting.
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
        db_running = hosting_repo.get_all_running()
    except Exception:
        logger.exception("reconciler: failed to query DB running containers")
        return

    if not db_running:
        return

    # 2. Ask Docker for ALL containers (running + exited + paused, etc.)
    #    Format: "name<TAB>status" where status is like "Up 3 hours" or "Exited (1) 2 minutes ago"
    try:
        code, stdout, stderr = await run_docker_command_async(
            ["ps", "-a", "--format", "{{.Names}}\t{{.Status}}"],
            timeout=15,
        )
        if code != 0:
            logger.error("reconciler: docker ps exited %d: %s — skipping this pass", code, stderr)
            return
    except Exception:
        logger.exception("reconciler: docker ps failed — skipping this pass")
        return

    # Build lookup: name → "up" | "exited" | "other"
    docker_state: dict[str, str] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 1)
        name = parts[0].strip()
        status_str = parts[1].strip().lower() if len(parts) > 1 else ""
        if status_str.startswith("up"):
            docker_state[name] = "up"
        elif status_str.startswith("exited"):
            docker_state[name] = "exited"
        else:
            docker_state[name] = "other"

    zombies = []
    exited = []
    for h in db_running:
        state = docker_state.get(h["container_name"])
        if state is None:
            zombies.append(h)
        elif state == "exited":
            exited.append(h)
        # state == "up" → healthy, nothing to do

    total_issues = len(zombies) + len(exited)
    if not total_issues:
        logger.debug("reconciler: all %d containers healthy", len(db_running))
        return

    # 3. Attempt to restart Exited containers.
    restarted = 0
    restart_failed = []
    for h in exited:
        try:
            rc, _, err = await run_docker_command_async(
                ["start", h["container_name"]], timeout=20
            )
            if rc == 0:
                restarted += 1
                logger.warning(
                    "reconciler: restarted exited container — hosting_id=%s container=%s",
                    h["hosting_id"], h["container_name"],
                )
            else:
                restart_failed.append(h)
                logger.error(
                    "reconciler: failed to restart container — hosting_id=%s container=%s error=%s",
                    h["hosting_id"], h["container_name"], err,
                )
        except Exception:
            restart_failed.append(h)
            logger.exception(
                "reconciler: exception restarting container — hosting_id=%s container=%s",
                h["hosting_id"], h["container_name"],
            )

    # 4. Mark unrecoverable exited containers as 'failed'.
    for h in restart_failed:
        try:
            hosting_repo.update_status(h["hosting_id"], "failed")
        except Exception:
            logger.exception("reconciler: failed to mark hosting_id=%s as failed", h["hosting_id"])

    # 5. Mark zombie containers (completely absent from Docker).
    for h in zombies:
        try:
            hosting_repo.update_status(h["hosting_id"], "zombie")
            logger.warning(
                "reconciler: zombie detected — hosting_id=%s container=%s "
                "was 'running' in DB but not found in docker ps -a",
                h["hosting_id"], h["container_name"],
            )
        except Exception:
            logger.exception("reconciler: failed to update status for hosting_id=%s", h["hosting_id"])

    hosting_repo.log_orchestrator_event(
        "system", 0, "reconcile",
        (
            f"reconciler: {len(db_running)} checked — "
            f"{restarted} restarted, {len(restart_failed)} failed, {len(zombies)} zombies"
        ),
        simulated=False,
    )
