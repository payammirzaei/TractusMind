from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.generation.factory import create_grounded_answer_service
from app.generation.llm import LLMConfigurationError, LLMGenerationError
from app.generation.models import GroundedAnswer

router = APIRouter(prefix="/v1", tags=["answers"])


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=4_000)


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

    try:
        return await service.answer(payload.question)
    except LLMGenerationError as exc:
        raise HTTPException(status_code=502, detail="Grounded answer generation failed") from exc
