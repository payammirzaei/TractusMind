from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.api.user_auth import require_user
from app.auth.store import UserIdentity
from app.conversations.store import ConversationAccessError

router = APIRouter(prefix="/v1/conversations", tags=["conversations"])


class ConversationSummary(BaseModel):
    conversation_id: str
    created_at: datetime
    updated_at: datetime


class ConversationTurnResponse(BaseModel):
    question: str
    answer: str


class ConversationHistoryResponse(BaseModel):
    conversation_id: str
    turns: list[ConversationTurnResponse]


@router.get("", response_model=list[ConversationSummary])
async def conversations(
    request: Request,
    user: Annotated[UserIdentity, Depends(require_user)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[ConversationSummary]:
    records = await request.app.state.conversation_store.list_owned_conversations(
        owner_user_id=user.user_id,
        limit=limit,
    )
    return [ConversationSummary(**record.__dict__) for record in records]


@router.get("/{conversation_id}", response_model=ConversationHistoryResponse)
async def conversation_history(
    conversation_id: UUID,
    request: Request,
    user: Annotated[UserIdentity, Depends(require_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ConversationHistoryResponse:
    resolved_id = str(conversation_id)
    try:
        exists = await request.app.state.conversation_store.assert_conversation_access(
            conversation_id=resolved_id,
            owner_user_id=user.user_id,
        )
    except ConversationAccessError as exc:
        raise HTTPException(status_code=404, detail="Unknown conversation") from exc
    if not exists:
        raise HTTPException(status_code=404, detail="Unknown conversation")

    turns = await request.app.state.conversation_store.load_history(
        conversation_id=resolved_id,
        owner_user_id=user.user_id,
        limit=limit,
        max_chars=200_000,
    )
    return ConversationHistoryResponse(
        conversation_id=resolved_id,
        turns=[ConversationTurnResponse(**turn.__dict__) for turn in turns],
    )
