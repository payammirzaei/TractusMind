import argparse
import time
from collections.abc import Sequence

import structlog

from app.core.config import get_settings
from app.ingestion.models import SourceDefinition
from app.ingestion.registry import get_enabled_sources
from app.observability.metrics import QUEUE_ENQUEUED
from app.workers.tasks import sync_source_task

logger = structlog.get_logger()


def enqueue_sources(sources: Sequence[SourceDefinition]) -> list[str]:
    source_ids: list[str] = []
    for source in sources:
        sync_source_task.send(source.id)
        QUEUE_ENQUEUED.labels(origin="scheduler").inc()
        source_ids.append(source.id)
    return source_ids


def enqueue_enabled_sources() -> list[str]:
    return enqueue_sources(get_enabled_sources())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tractusmind-scheduler")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Enqueue enabled sources once and exit.",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    settings = get_settings()

    while True:
        source_ids = enqueue_enabled_sources()
        logger.info(
            "source_sync_cycle_enqueued",
            source_ids=source_ids,
            source_count=len(source_ids),
            interval_seconds=settings.source_sync_interval_seconds,
        )
        if args.once:
            return
        time.sleep(settings.source_sync_interval_seconds)


if __name__ == "__main__":
    main()
