import asyncio

import dramatiq
import structlog

from app.workers.broker import broker  # noqa: F401
from app.workers.sync import run_source_sync

logger = structlog.get_logger()


@dramatiq.actor(max_retries=3)
def healthcheck_task() -> str:
    logger.info("worker_healthcheck")
    return "ok"


@dramatiq.actor(max_retries=3)
def sync_source_task(source_id: str) -> dict[str, object]:
    logger.info("source_sync_started", source_id=source_id)
    return asyncio.run(run_source_sync(source_id))
