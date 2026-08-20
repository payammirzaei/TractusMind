import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.api.routes.ask import router as ask_router
from app.api.routes.conversations import router as conversations_router
from app.api.routes.feedback import router as feedback_router
from app.api.routes.health import router as health_router
from app.api.routes.interaction_ops import router as interaction_ops_router
from app.api.routes.metrics import router as metrics_router
from app.api.routes.ops import router as ops_router
from app.api.routes.quality_ops import router as quality_ops_router
from app.api.routes.user_ops import router as user_ops_router
from app.auth import AuthStore
from app.conversations import ConversationStore
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db import verify_database_revision
from app.infra.postgres import create_postgres_engine
from app.infra.qdrant import create_qdrant_client
from app.infra.redis import create_redis_client
from app.observability.http import observe_http_request
from app.observability.tracing import configure_tracing
from app.quality import QualityStore

settings = get_settings()
configure_logging(settings.log_level)
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    postgres = create_postgres_engine(settings)
    try:
        database_revision = await verify_database_revision(postgres)
    except Exception:
        await postgres.dispose()
        raise

    app.state.postgres = postgres
    app.state.redis = create_redis_client(settings)
    app.state.qdrant = create_qdrant_client(settings)
    app.state.auth_store = AuthStore(app.state.postgres)
    app.state.conversation_store = ConversationStore(app.state.postgres)
    app.state.quality_store = QualityStore(app.state.postgres)
    app.state.answer_service = None
    logger.info(
        "application_started",
        environment=settings.app_env,
        database_revision=database_revision,
    )

    yield

    if app.state.answer_service is not None:
        await app.state.answer_service.close()
    await app.state.postgres.dispose()
    await app.state.redis.aclose()
    await app.state.qdrant.close()
    if app.state.tracer_provider is not None:
        await asyncio.to_thread(app.state.tracer_provider.shutdown)
    logger.info("application_stopped")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Source-grounded AI engineering copilot for the Tractus-X ecosystem.",
    lifespan=lifespan,
)
app.include_router(health_router)
app.include_router(ask_router)
app.include_router(conversations_router)
app.include_router(feedback_router)
app.include_router(ops_router)
app.include_router(interaction_ops_router)
app.include_router(quality_ops_router)
app.include_router(user_ops_router)
app.include_router(metrics_router)
app.middleware("http")(observe_http_request)
app.state.tracer_provider = configure_tracing(app, settings)


@app.get("/", tags=["system"])
async def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "status": "running",
        "docs": "/docs",
    }
