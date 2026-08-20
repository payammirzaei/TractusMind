import secrets
from typing import Annotated

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


async def require_ops_admin(
    x_tractusmind_admin_key: Annotated[str | None, Header()] = None,
) -> None:
    configured = get_settings().ops_admin_key
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Operations API is disabled until OPS_ADMIN_KEY is configured",
        )
    if x_tractusmind_admin_key is None or not secrets.compare_digest(
        x_tractusmind_admin_key,
        configured,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid operations admin key",
        )
