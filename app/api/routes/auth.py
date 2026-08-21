from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.auth.store import UserRole
from app.core.config import get_settings

router = APIRouter(prefix="/v1/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=1024)


class LoginResponse(BaseModel):
    token: str
    user_id: str
    display_name: str
    username: str | None
    role: UserRole
    auth_type: str
    expires_in: int


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, request: Request) -> LoginResponse:
    settings = get_settings()
    if not settings.session_signing_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Local sign-in is not configured",
        )

    user = await request.app.state.auth_store.authenticate_password(
        payload.username,
        payload.password,
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = request.app.state.auth_store.issue_session(
        user,
        signing_key=settings.session_signing_key,
        ttl_seconds=settings.session_ttl_seconds,
    )
    return LoginResponse(
        token=token,
        user_id=user.user_id,
        display_name=user.display_name,
        username=user.username,
        role=user.role,
        auth_type=user.auth_type,
        expires_in=settings.session_ttl_seconds,
    )
