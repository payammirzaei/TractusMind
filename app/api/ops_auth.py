import secrets
from typing import Annotated

from fastapi import Header, HTTPException, Request, status

from app.api.user_auth import optional_user
from app.auth.store import UserIdentity, UserRole
from app.core.config import get_settings


async def _require_role(
    request: Request,
    *,
    required: UserRole,
    authorization: str | None,
    admin_key: str | None,
) -> UserIdentity | None:
    configured = get_settings().ops_admin_key
    if (
        admin_key is not None
        and configured
        and secrets.compare_digest(admin_key, configured)
    ):
        return None

    user = await optional_user(request, authorization)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Operations authentication required",
        )
    if not user.role.allows(required):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{required.value} role required",
        )
    return user


async def require_ops_operator(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_tractusmind_admin_key: Annotated[str | None, Header()] = None,
) -> UserIdentity | None:
    return await _require_role(
        request,
        required=UserRole.OPERATOR,
        authorization=authorization,
        admin_key=x_tractusmind_admin_key,
    )


async def require_ops_admin(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_tractusmind_admin_key: Annotated[str | None, Header()] = None,
) -> UserIdentity | None:
    return await _require_role(
        request,
        required=UserRole.ADMIN,
        authorization=authorization,
        admin_key=x_tractusmind_admin_key,
    )
