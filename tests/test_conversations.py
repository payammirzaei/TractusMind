from contextlib import nullcontext

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.ask import router as ask_router
from app.api.routes.feedback import router as feedback_router
from app.conversations.store import FeedbackRecord, InteractionIdentity
from app.generation.llm import LLMGenerationError
from app.generation.models import GroundedAnswer
from app.observability.metrics import observe_stage
from app.routing.models import QueryIntent, QueryRoute

_CONVERSATION_ID = "11111111-1111-4111-8111-111111111111"
_INTERACTION_ID = "22222222-2222-4222-8222-222222222222"
_FEEDBACK_ID = "33333333-3333-4333-8333-333333333333"


class FakeAnswerService:
    async def answer(self, question: str) -> GroundedAnswer:
        with observe_stage("retrieval", "sdk"):
            with nullcontext():
                pass
        return GroundedAnswer(
            question=question,
            answer="Use the SDK evidence [S1].",
            grounded=True,
            abstained=False,
            evidence_count=1,
            route=QueryRoute(intent=QueryIntent.SDK),
            model="test-model",
        )


class FailingAnswerService:
    async def answer(self, _question: str) -> GroundedAnswer:
        with observe_stage("generation", "sdk"):
            raise LLMGenerationError("provider failed")


class FakeConversationStore:
    def __init__(self) -> None:
        self.answer_kwargs: dict[str, object] | None = None
        self.failure_kwargs: dict[str, object] | None = None
        self.feedback_exists = True

    async def record_answer(self, **kwargs) -> InteractionIdentity:
        self.answer_kwargs = kwargs
        return InteractionIdentity(
            interaction_id=_INTERACTION_ID,
            conversation_id=str(kwargs["conversation_id"] or _CONVERSATION_ID),
        )

    async def record_failure(self, **kwargs) -> InteractionIdentity:
        self.failure_kwargs = kwargs
        return InteractionIdentity(
            interaction_id=_INTERACTION_ID,
            conversation_id=str(kwargs["conversation_id"] or _CONVERSATION_ID),
        )

    async def upsert_feedback(self, **kwargs) -> FeedbackRecord | None:
        if not self.feedback_exists:
            return None
        return FeedbackRecord(
            feedback_id=_FEEDBACK_ID,
            interaction_id=str(kwargs["interaction_id"]),
            rating=str(kwargs["rating"]),
            reason=kwargs.get("reason"),
            comment=kwargs.get("comment"),
        )


def _app(service) -> tuple[FastAPI, FakeConversationStore]:
    app = FastAPI()
    store = FakeConversationStore()
    app.state.answer_service = service
    app.state.conversation_store = store
    app.include_router(ask_router)
    app.include_router(feedback_router)
    return app, store


def test_ask_persists_trace_and_returns_conversation_identity() -> None:
    app, store = _app(FakeAnswerService())

    response = TestClient(app).post(
        "/v1/ask",
        json={
            "question": "How do I use the SDK?",
            "conversation_id": _CONVERSATION_ID,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["interaction_id"] == _INTERACTION_ID
    assert payload["conversation_id"] == _CONVERSATION_ID
    assert store.answer_kwargs is not None
    durations = store.answer_kwargs["stage_durations"]
    assert isinstance(durations, dict)
    assert "retrieval" in durations
    assert float(store.answer_kwargs["total_duration_seconds"]) >= 0.0


def test_generation_failure_is_persisted_before_http_error() -> None:
    app, store = _app(FailingAnswerService())

    response = TestClient(app).post(
        "/v1/ask",
        json={"question": "How do I use the SDK?"},
    )

    assert response.status_code == 502
    assert store.failure_kwargs is not None
    assert store.failure_kwargs["error_type"] == "LLMGenerationError"
    durations = store.failure_kwargs["stage_durations"]
    assert isinstance(durations, dict)
    assert "generation" in durations


def test_feedback_endpoint_upserts_completed_interaction_feedback() -> None:
    app, _store = _app(FakeAnswerService())

    response = TestClient(app).post(
        "/v1/feedback",
        json={
            "interaction_id": _INTERACTION_ID,
            "rating": "down",
            "reason": "citation",
            "comment": "The source did not answer my exact question.",
        },
    )

    assert response.status_code == 200
    assert response.json()["feedback_id"] == _FEEDBACK_ID
    assert response.json()["rating"] == "down"


def test_feedback_rejects_unknown_interaction() -> None:
    app, store = _app(FakeAnswerService())
    store.feedback_exists = False

    response = TestClient(app).post(
        "/v1/feedback",
        json={"interaction_id": _INTERACTION_ID, "rating": "up"},
    )

    assert response.status_code == 404
