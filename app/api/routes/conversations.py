from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.user_auth import require_user
from app.auth.store import UserIdentity
from app.conversations.store import ConversationAccessError, ConversationRecord, InteractionRecord
from app.generation.models import AnswerCitation, VerificationReport
from app.routing.models import QueryRoute

router = APIRouter(prefix="/v1/conversations", tags=["conversations"])


class ConversationSummary(BaseModel):
    conversation_id: str
    created_at: datetime
    updated_at: datetime
    title: str
    preview: str | None = None
    turn_count: int = Field(ge=0)


class ConversationTurnResponse(BaseModel):
    interaction_id: str
    conversation_id: str
    question: str
    answer: str
    grounded: bool
    abstained: bool
    evidence_count: int = Field(ge=0)
    citations: list[AnswerCitation] = Field(default_factory=list)
    verification: VerificationReport | None = None
    route: QueryRoute | None = None
    model: str | None = None


class ConversationHistoryResponse(BaseModel):
    conversation_id: str
    turns: list[ConversationTurnResponse]


def _compact_text(value: str, *, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(1, limit - 1)].rstrip(" ,.;:-") + "…"


async def _conversation_summary(
    request: Request,
    record: ConversationRecord,
    *,
    owner_user_id: str,
) -> ConversationSummary:
    # Conversation rows intentionally stay lightweight. Derive a human-readable title and
    # current-topic preview from the persisted turns so existing sessions become useful without
    # a schema migration or a second LLM call.
    turns = await request.app.state.conversation_store.load_history(
        conversation_id=record.conversation_id,
        owner_user_id=owner_user_id,
        limit=500,
        max_chars=500_000,
    )
    if not turns:
        return ConversationSummary(
            conversation_id=record.conversation_id,
            created_at=record.created_at,
            updated_at=record.updated_at,
            title="New conversation",
            preview=None,
            turn_count=0,
        )

    first_question = turns[0].question
    last_question = turns[-1].question
    preview = None
    if len(turns) > 1 and last_question.strip() != first_question.strip():
        preview = _compact_text(last_question, limit=96)

    return ConversationSummary(
        conversation_id=record.conversation_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
        title=_compact_text(first_question, limit=72),
        preview=preview,
        turn_count=len(turns),
    )


def _historical_turn(record: InteractionRecord) -> ConversationTurnResponse | None:
    if not record.answer:
        return None
    return ConversationTurnResponse(
        interaction_id=record.interaction_id,
        conversation_id=record.conversation_id,
        question=record.question,
        answer=record.answer,
        grounded=record.grounded,
        abstained=record.abstained,
        evidence_count=record.evidence_count,
        citations=record.citations_json or [],
        verification=record.verification_json,
        route=record.route_json,
        model=record.model,
    )


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
    summaries: list[ConversationSummary] = []
    for record in records:
        summaries.append(
            await _conversation_summary(
                request,
                record,
                owner_user_id=user.user_id,
            )
        )
    return summaries


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

    # AnswerInteraction already stores the complete provenance payload. Rehydrate it here instead
    # of reducing historical turns to plain question/answer text.
    records = await request.app.state.conversation_store.list_interactions(
        conversation_id=resolved_id,
        status="completed",
        limit=limit,
    )
    records.reverse()
    turns = [turn for record in records if (turn := _historical_turn(record)) is not None]
    return ConversationHistoryResponse(
        conversation_id=resolved_id,
        turns=turns,
    )
