from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.observability.metrics import FEEDBACK

router = APIRouter(prefix="/v1", tags=["feedback"])


class FeedbackRequest(BaseModel):
    interaction_id: UUID
    rating: Literal["up", "down"]
    reason: str | None = Field(default=None, max_length=128)
    comment: str | None = Field(default=None, max_length=2_000)


class FeedbackResponse(BaseModel):
    feedback_id: str
    interaction_id: str
    rating: Literal["up", "down"]
    reason: str | None = None
    comment: str | None = None


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    payload: FeedbackRequest,
    request: Request,
) -> FeedbackResponse:
    record = await request.app.state.conversation_store.upsert_feedback(
        interaction_id=str(payload.interaction_id),
        rating=payload.rating,
        reason=payload.reason,
        comment=payload.comment,
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown completed interaction",
        )

    FEEDBACK.labels(rating=record.rating).inc()
    return FeedbackResponse(
        feedback_id=record.feedback_id,
        interaction_id=record.interaction_id,
        rating=record.rating,
        reason=record.reason,
        comment=record.comment,
    )
