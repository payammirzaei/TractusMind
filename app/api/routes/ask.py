from time import perf_counter
from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.generation.factory import create_grounded_answer_service
from app.generation.llm import LLMConfigurationError, LLMGenerationError
from app.generation.models import GroundedAnswer
from app.observability.trace_context import (
    begin_answer_trace,
    current_trace_id,
    finish_answer_trace,
)

router = APIRouter(prefix="/v1", tags=["answers"])
logger = structlog.get_logger()


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=4_000)
    conversation_id: UUID | None = None


@router.post("/ask", response_model=GroundedAnswer)
async def ask(payload: AskRequest, request: Request) -> GroundedAnswer:
    service = getattr(request.app.state, "answer_service", None)
    if service is None:
        try:
            service = create_grounded_answer_service(
                get_settings(),
                request.app.state.qdrant,
            )
        except LLMConfigurationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        request.app.state.answer_service = service

    conversation_id = str(payload.conversation_id) if payload.conversation_id else None
    started = perf_counter()
    token = begin_answer_trace()
    try:
        answer = await service.answer(payload.question)
    except LLMGenerationError as exc:
        trace = finish_answer_trace(token)
        await _persist_failure(
            request,
            question=payload.question,
            conversation_id=conversation_id,
            error_type=type(exc).__name__,
            stage_durations=trace.stage_durations,
            total_duration_seconds=perf_counter() - started,
            trace_id=current_trace_id(),
        )
        raise HTTPException(status_code=502, detail="Grounded answer generation failed") from exc
    except Exception:
        finish_answer_trace(token)
        raise

    trace = finish_answer_trace(token)
    try:
        identity = await request.app.state.conversation_store.record_answer(
            question=payload.question,
            answer=answer,
            conversation_id=conversation_id,
            stage_durations=trace.stage_durations,
            total_duration_seconds=perf_counter() - started,
            trace_id=current_trace_id(),
        )
    except Exception as exc:
        logger.exception(
            "answer_persistence_failed",
            error_type=type(exc).__name__,
        )
        return answer

    answer.interaction_id = identity.interaction_id
    answer.conversation_id = identity.conversation_id
    return answer


async def _persist_failure(
    request: Request,
    *,
    question: str,
    conversation_id: str | None,
    error_type: str,
    stage_durations: dict[str, float],
    total_duration_seconds: float,
    trace_id: str | None,
) -> None:
    try:
        await request.app.state.conversation_store.record_failure(
            question=question,
            conversation_id=conversation_id,
            error_type=error_type,
            stage_durations=stage_durations,
            total_duration_seconds=total_duration_seconds,
            trace_id=trace_id,
        )
    except Exception as exc:
        logger.exception(
            "answer_failure_persistence_failed",
            error_type=type(exc).__name__,
        )
