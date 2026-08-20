import dramatiq
import structlog

from app.workers.broker import broker  # noqa: F401

logger = structlog.get_logger()


@dramatiq.actor(max_retries=3)
def healthcheck_task() -> str:
    logger.info("worker_healthcheck")
    return "ok"
