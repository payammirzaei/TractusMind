from typing import Annotated, Literal
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.user_auth import optional_user
from app.auth.store import UserIdentity
from app.conversations.store import ConversationAccessError
from app.observability.metrics import FEEDBACK

router = APIRouter(prefix="/v1", tags=["feedback"])
logger = structlog.get_logger()


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
    user: Annotated[UserIdentity | None, Depends(optional_user)],
) -> FeedbackResponse:
    try:
        record = await request.app.state.conversation_store.upsert_feedback(
            interaction_id=str(payload.interaction_id),
            actor_user_id=user.user_id if user is not None else None,
            rating=payload.rating,
            reason=payload.reason,
            comment=payload.comment,
        )
    except ConversationAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown completed interaction",
        ) from exc
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown completed interaction",
        )

    if record.rating == "down":
        try:
            await request.app.state.quality_store.ensure_review(
                interaction_id=record.interaction_id,
                trigger="feedback_down",
            )
        except Exception as exc:
            logger.exception(
                "quality_review_capture_failed",
                trigger="feedback_down",
                error_type=type(exc).__name__,
            )

    FEEDBACK.labels(rating=record.rating).inc()
    return FeedbackResponse(
        feedback_id=record.feedback_id,
        interaction_id=record.interaction_id,
        rating=record.rating,
        reason=record.reason,
        comment=record.comment,
    )
