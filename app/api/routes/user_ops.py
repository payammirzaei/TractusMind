from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

from app.api.ops_auth import require_ops_admin
from app.auth.models import UserAccount
from app.auth.store import (
    ExternalRoleManagedError,
    UserCredential,
    UserIdentity,
    UserRole,
)
from app.conversations.models import Conversation

router = APIRouter(
    prefix="/v1/ops/users",
    tags=["operations"],
    dependencies=[Depends(require_ops_admin)],
)


class UserResponse(BaseModel):
    user_id: str
    display_name: str
    username: str | None = None
    api_key_prefix: str | None
    enabled: bool
    role: UserRole
    auth_type: str


class UserCredentialResponse(UserResponse):
    api_key: str


class CreateUserRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    role: UserRole = UserRole.USER


class CreatePasswordUserRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=12, max_length=1_024)
    role: UserRole = UserRole.USER


class UserStateRequest(BaseModel):
    enabled: bool | None = None
    role: UserRole | None = None


def _user(identity: UserIdentity) -> UserResponse:
    return UserResponse(**identity.__dict__)


def _credential(credential: UserCredential) -> UserCredentialResponse:
    return UserCredentialResponse(
        **credential.user.__dict__,
        api_key=credential.api_key,
    )


@router.get("", response_model=list[UserResponse])
async def users(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
) -> list[UserResponse]:
    records = await request.app.state.auth_store.list_users(limit=limit)
    return [_user(record) for record in records]


@router.post("", response_model=UserCredentialResponse)
async def create_user(
    payload: CreateUserRequest,
    request: Request,
) -> UserCredentialResponse:
    display_name = payload.display_name.strip()
    if not display_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="display_name must not be blank",
        )
    credential = await request.app.state.auth_store.create_user(
        display_name,
        role=payload.role,
    )
    return _credential(credential)


@router.post(
    "/password",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_password_user(
    payload: CreatePasswordUserRequest,
    request: Request,
) -> UserResponse:
    try:
        identity = await request.app.state.auth_store.set_password_user(
            username=payload.username,
            password=payload.password,
            display_name=payload.display_name,
            role=payload.role,
        )
    except ValueError as exc:
        message = str(exc)
        code = (
            status.HTTP_409_CONFLICT
            if "already in use" in message
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=code, detail=message) from exc
    return _user(identity)


@router.post("/{user_id}/rotate", response_model=UserCredentialResponse)
async def rotate_user_key(user_id: UUID, request: Request) -> UserCredentialResponse:
    credential = await request.app.state.auth_store.rotate_api_key(str(user_id))
    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unknown user or identity does not use an API key",
        )
    return _credential(credential)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user_state(
    user_id: UUID,
    payload: UserStateRequest,
    request: Request,
) -> UserResponse:
    if payload.enabled is None and payload.role is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one of enabled or role is required",
        )
    try:
        identity = await request.app.state.auth_store.update_user(
            str(user_id),
            enabled=payload.enabled,
            role=payload.role,
        )
    except ExternalRoleManagedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if identity is None:
        raise HTTPException(status_code=404, detail="Unknown user")
    return _user(identity)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    request: Request,
    actor: Annotated[UserIdentity | None, Depends(require_ops_admin)],
) -> Response:
    target_id = str(user_id)
    if actor is not None and actor.user_id == target_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You cannot delete your current account",
        )

    store = request.app.state.auth_store
    await store.ensure_schema()
    async with store.sessions.begin() as session:
        user = await session.get(UserAccount, target_id)
        if user is None:
            raise HTTPException(status_code=404, detail="Unknown user")

        if user.role == UserRole.ADMIN.value and user.enabled:
            enabled_admins = await session.scalar(
                select(func.count())
                .select_from(UserAccount)
                .where(
                    UserAccount.role == UserRole.ADMIN.value,
                    UserAccount.enabled.is_(True),
                )
            )
            if int(enabled_admins or 0) <= 1:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="The last enabled admin cannot be deleted",
                )

        # Keep historical conversations but detach them from the deleted identity.
        await session.execute(
            update(Conversation)
            .where(Conversation.owner_user_id == target_id)
            .values(owner_user_id=None)
        )
        await session.delete(user)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
