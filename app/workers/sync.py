from dataclasses import asdict

import structlog
from qdrant_client import AsyncQdrantClient
from redis.exceptions import LockNotOwnedError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings, get_settings
from app.infra.postgres import create_postgres_engine
from app.infra.qdrant import create_qdrant_client
from app.infra.redis import create_redis_client
from app.ingestion.pipeline import SourceIngestionPipeline
from app.ingestion.registry import get_source
from app.ingestion.sync import IncrementalSourceSync
from app.retrieval.factory import create_hybrid_retrieval_service
from app.state.store import SourceStateStore

logger = structlog.get_logger()


async def run_source_sync(
    source_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, object]:
    """Run one source sync with a distributed per-source Redis lock."""

    resolved_settings = settings or get_settings()
    source = get_source(source_id)
    redis = create_redis_client(resolved_settings)
    lock = redis.lock(
        f"tractusmind:source-sync:{source_id}",
        timeout=resolved_settings.source_sync_lock_seconds,
        blocking=False,
    )
    acquired = await lock.acquire(blocking=False)
    if not acquired:
        await redis.aclose()
        logger.info("source_sync_skipped_locked", source_id=source_id)
        return {"status": "locked", "source_id": source_id}

    engine: AsyncEngine | None = None
    qdrant: AsyncQdrantClient | None = None
    try:
        engine = create_postgres_engine(resolved_settings)
        qdrant = create_qdrant_client(resolved_settings)
        state = SourceStateStore(engine)
        retrieval = create_hybrid_retrieval_service(resolved_settings, qdrant)
        async with SourceIngestionPipeline(
            token=resolved_settings.github_token
        ) as pipeline:
            sync = IncrementalSourceSync(
                pipeline=pipeline,
                retrieval=retrieval,
                state=state,
            )
            result = await sync.sync(source)

        payload = {"status": "succeeded", **asdict(result)}
        logger.info("source_sync_succeeded", **payload)
        return payload
    finally:
        if qdrant is not None:
            await qdrant.close()
        if engine is not None:
            await engine.dispose()
        try:
            await lock.release()
        except LockNotOwnedError:
            logger.warning("source_sync_lock_expired", source_id=source_id)
        await redis.aclose()
