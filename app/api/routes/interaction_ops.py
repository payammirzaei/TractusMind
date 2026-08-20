from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from app.api.ops_auth import require_ops_admin
from app.conversations.store import InteractionRecord

router = APIRouter(
    prefix="/v1/ops",
    tags=["operations"],
    dependencies=[Depends(require_ops_admin)],
)


class InteractionOpsStatus(BaseModel):
    interaction_id: str
    conversation_id: str
    request_id: str | None
    question: str
    answer: str | None
    status: str
    grounded: bool
    abstained: bool
    evidence_count: int
    model: str | None
    intent: str | None
    route: dict[str, object] | None
    citations: list[dict[str, object]] | None
    verification: dict[str, object] | None
    stage_durations: dict[str, float] | None
    total_duration_seconds: float | None
    trace_id: str | None
    error_type: str | None
    created_at: datetime
    feedback_rating: str | None
    feedback_reason: str | None
    feedback_comment: str | None


class FeedbackSummary(BaseModel):
    counts: dict[str, int]


def _response(record: InteractionRecord) -> InteractionOpsStatus:
    return InteractionOpsStatus(
        interaction_id=record.interaction_id,
        conversation_id=record.conversation_id,
        request_id=record.request_id,
        question=record.question,
        answer=record.answer,
        status=record.status,
        grounded=record.grounded,
        abstained=record.abstained,
        evidence_count=record.evidence_count,
        model=record.model,
        intent=record.intent,
        route=record.route_json,
        citations=record.citations_json,
        verification=record.verification_json,
        stage_durations=record.stage_durations_json,
        total_duration_seconds=record.total_duration_seconds,
        trace_id=record.trace_id,
        error_type=record.error_type,
        created_at=record.created_at,
        feedback_rating=record.feedback_rating,
        feedback_reason=record.feedback_reason,
        feedback_comment=record.feedback_comment,
    )


@router.get("/interactions", response_model=list[InteractionOpsStatus])
async def interactions(
    request: Request,
    conversation_id: Annotated[UUID | None, Query()] = None,
    interaction_status: Annotated[
        Literal["completed", "failed"] | None,
        Query(alias="status"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[InteractionOpsStatus]:
    records = await request.app.state.conversation_store.list_interactions(
        conversation_id=str(conversation_id) if conversation_id else None,
        status=interaction_status,
        limit=limit,
    )
    return [_response(record) for record in records]


@router.get("/interactions/{interaction_id}", response_model=InteractionOpsStatus)
async def interaction(
    interaction_id: UUID,
    request: Request,
) -> InteractionOpsStatus:
    record = await request.app.state.conversation_store.get_interaction(
        str(interaction_id)
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown interaction id",
        )
    return _response(record)


@router.get("/feedback/summary", response_model=FeedbackSummary)
async def feedback_summary(request: Request) -> FeedbackSummary:
    return FeedbackSummary(
        counts=await request.app.state.conversation_store.feedback_counts()
    )
