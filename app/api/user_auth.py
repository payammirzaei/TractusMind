from typing import Annotated

from fastapi import Header, HTTPException, Request, status

from app.auth.store import UserIdentity


async def optional_user(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> UserIdentity | None:
    if authorization is None:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.casefold() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
        )
    user = await request.app.state.auth_store.authenticate(token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
        )
    return user


async def require_user(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> UserIdentity:
    user = await optional_user(request, authorization)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user
