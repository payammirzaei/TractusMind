from datetime import datetime
from typing import Annotated, Literal

import structlog
from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field, field_validator

from app.activity import ActivityRecord
from app.api.ops_auth import require_ops_operator
from app.api.user_auth import optional_user
from app.auth.store import UserIdentity
from app.core.config import get_settings

logger = structlog.get_logger()

router = APIRouter(prefix="/v1/activity", tags=["activity"])
ops_router = APIRouter(
    prefix="/v1/ops",
    tags=["operations"],
    dependencies=[Depends(require_ops_operator)],
)

MetadataValue = str | int | float | bool | None


class ClientActivityEvent(BaseModel):
    event_type: Literal["page_view", "click"]
    session_id: str = Field(min_length=1, max_length=64)
    visitor_id: str = Field(min_length=1, max_length=64)
    path: str = Field(min_length=1, max_length=2048)
    referrer: str | None = Field(default=None, max_length=2048)
    target: str | None = Field(default=None, max_length=512)
    metadata: dict[str, MetadataValue] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, MetadataValue]) -> dict[str, MetadataValue]:
        if len(value) > 20:
            raise ValueError("metadata may contain at most 20 keys")
        for key, item in value.items():
            if not key or len(key) > 64:
                raise ValueError("metadata keys must be 1-64 characters")
            if isinstance(item, str) and len(item) > 256:
                raise ValueError("metadata string values may be at most 256 characters")
        return value


class ActivityAccepted(BaseModel):
    accepted: bool


class ActivityOpsStatus(BaseModel):
    event_id: str
    event_type: str
    user_id: str | None
    session_id: str | None
    visitor_id: str | None
    request_id: str | None
    ip_address: str | None
    method: str | None
    path: str
    status_code: int | None
    duration_ms: float | None
    referrer: str | None
    user_agent: str | None
    target: str | None
    metadata: dict[str, object] | None
    created_at: datetime


def _client_ip(request: Request) -> str | None:
    if get_settings().trust_forwarded_for:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            address = forwarded.split(",", 1)[0].strip()
            if address:
                return address[:64]
    if request.client is None:
        return None
    return request.client.host[:64]


def _response(record: ActivityRecord) -> ActivityOpsStatus:
    return ActivityOpsStatus(
        event_id=record.event_id,
        event_type=record.event_type,
        user_id=record.user_id,
        session_id=record.session_id,
        visitor_id=record.visitor_id,
        request_id=record.request_id,
        ip_address=record.ip_address,
        method=record.method,
        path=record.path,
        status_code=record.status_code,
        duration_ms=record.duration_ms,
        referrer=record.referrer,
        user_agent=record.user_agent,
        target=record.target,
        metadata=record.metadata_json,
        created_at=record.created_at,
    )


@router.post(
    "/events",
    response_model=ActivityAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def activity_event(
    payload: ClientActivityEvent,
    request: Request,
    user: Annotated[UserIdentity | None, Depends(optional_user)],
) -> ActivityAccepted:
    try:
        await request.app.state.activity_store.record_event(
            event_type=payload.event_type,
            path=payload.path,
            user_id=user.user_id if user else None,
            session_id=payload.session_id,
            visitor_id=payload.visitor_id,
            request_id=getattr(request.state, "request_id", None),
            ip_address=_client_ip(request),
            referrer=payload.referrer or request.headers.get("referer"),
            user_agent=request.headers.get("user-agent"),
            target=payload.target,
            metadata_json=dict(payload.metadata) or None,
        )
    except Exception as exc:
        logger.warning(
            "activity_event_store_failed",
            error_type=type(exc).__name__,
            event_type=payload.event_type,
        )
        return ActivityAccepted(accepted=False)
    return ActivityAccepted(accepted=True)


@ops_router.get("/activity", response_model=list[ActivityOpsStatus])
async def activity_log(
    request: Request,
    event_type: Annotated[
        Literal["page_view", "click", "http_request"] | None,
        Query(),
    ] = None,
    path: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[ActivityOpsStatus]:
    records = await request.app.state.activity_store.list_events(
        event_type=event_type,
        path_contains=path,
        limit=limit,
    )
    return [_response(record) for record in records]
