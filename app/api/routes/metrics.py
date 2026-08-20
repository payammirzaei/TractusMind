import secrets
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.core.config import get_settings

router = APIRouter(tags=["observability"])


@router.get("/metrics", include_in_schema=False)
async def metrics(
    x_tractusmind_metrics_key: Annotated[
        str | None,
        Header(alias="X-TractusMind-Metrics-Key"),
    ] = None,
) -> Response:
    settings = get_settings()
    if not settings.metrics_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    if settings.app_env.lower() != "development":
        configured = settings.metrics_admin_key or settings.ops_admin_key
        if not configured:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Metrics endpoint requires METRICS_ADMIN_KEY or OPS_ADMIN_KEY",
            )
        if x_tractusmind_metrics_key is None or not secrets.compare_digest(
            x_tractusmind_metrics_key,
            configured,
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid metrics key",
            )

    return Response(
        content=generate_latest(),
        headers={"Content-Type": CONTENT_TYPE_LATEST},
    )
