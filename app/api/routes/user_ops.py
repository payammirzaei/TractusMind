from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.ops_auth import require_ops_admin
from app.auth.store import UserCredential, UserIdentity

router = APIRouter(
    prefix="/v1/ops/users",
    tags=["operations"],
    dependencies=[Depends(require_ops_admin)],
)


class UserResponse(BaseModel):
    user_id: str
    display_name: str
    api_key_prefix: str
    enabled: bool


class UserCredentialResponse(UserResponse):
    api_key: str


class CreateUserRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)


class UserStateRequest(BaseModel):
    enabled: bool


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
    credential = await request.app.state.auth_store.create_user(payload.display_name)
    return _credential(credential)


@router.post("/{user_id}/rotate", response_model=UserCredentialResponse)
async def rotate_user_key(user_id: UUID, request: Request) -> UserCredentialResponse:
    credential = await request.app.state.auth_store.rotate_api_key(str(user_id))
    if credential is None:
        raise HTTPException(status_code=404, detail="Unknown user")
    return _credential(credential)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user_state(
    user_id: UUID,
    payload: UserStateRequest,
    request: Request,
) -> UserResponse:
    identity = await request.app.state.auth_store.set_enabled(str(user_id), payload.enabled)
    if identity is None:
        raise HTTPException(status_code=404, detail="Unknown user")
    return _user(identity)
