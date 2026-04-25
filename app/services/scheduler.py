"""
Scheduler abstraction layer.

Current implementation: thin asyncio wrapper (inline tasks in lifespan).
Future migration path: swap body of schedule_job() for Celery/ARQ/Dramatiq
without touching any call sites.

Usage:
    from app.services.scheduler import schedule_job

    schedule_job(my_task_fn, interval_seconds=300)
"""
import asyncio
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

# Kept as a module-level set so asyncio does not GC running tasks.
_tasks: set = set()


def schedule_job(fn: Callable, interval: int) -> None:
    """
    Schedule a callable to run repeatedly every `interval` seconds.

    Supports both sync and async callables:
    - async functions are awaited directly on the event loop
    - sync functions are dispatched to a thread executor
    """
    async def _loop():
        logger.info("job %s started (interval=%ds)", fn.__name__, interval)
        while True:
            t0 = asyncio.get_event_loop().time()
            try:
                if asyncio.iscoroutinefunction(fn):
                    await fn()
                else:
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, fn)
                elapsed = asyncio.get_event_loop().time() - t0
                logger.info("job %s completed in %.2fs", fn.__name__, elapsed)
            except Exception as e:
                logger.error("job %s failed: %s", fn.__name__, e, exc_info=True)
            await asyncio.sleep(interval)

    task = asyncio.create_task(_loop())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
