from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.user_auth import require_user
from app.auth.store import UserIdentity, UserRole

router = APIRouter(prefix="/v1", tags=["identity"])


class CurrentUserResponse(BaseModel):
    user_id: str
    display_name: str
    role: UserRole
    auth_type: str


@router.get("/me", response_model=CurrentUserResponse)
async def current_user(
    user: Annotated[UserIdentity, Depends(require_user)],
) -> CurrentUserResponse:
    return CurrentUserResponse(
        user_id=user.user_id,
        display_name=user.display_name,
        role=user.role,
        auth_type=user.auth_type,
    )
