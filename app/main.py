from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.infra.postgres import create_postgres_engine
from app.infra.qdrant import create_qdrant_client
from app.infra.redis import create_redis_client

settings = get_settings()
configure_logging(settings.log_level)
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.postgres = create_postgres_engine(settings)
    app.state.redis = create_redis_client(settings)
    app.state.qdrant = create_qdrant_client(settings)
    logger.info("application_started", environment=settings.app_env)

    yield

    await app.state.postgres.dispose()
    await app.state.redis.aclose()
    await app.state.qdrant.close()
    logger.info("application_stopped")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Source-grounded AI engineering copilot for the Tractus-X ecosystem.",
    lifespan=lifespan,
)
app.include_router(health_router)


@app.get("/", tags=["system"])
async def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "status": "running",
        "docs": "/docs",
    }
