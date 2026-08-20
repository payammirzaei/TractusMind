from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.ask import router as ask_router
from app.api.routes.feedback import router as feedback_router
from app.conversations.history import ConversationTurn
from app.conversations.store import FeedbackRecord, InteractionIdentity
from app.generation.llm import LLMGenerationError
from app.generation.models import GroundedAnswer
from app.observability.http import observe_http_request
from app.observability.metrics import observe_stage
from app.observability.trace_context import record_trace_metadata
from app.routing.models import QueryIntent, QueryRoute

_CONVERSATION_ID = "11111111-1111-4111-8111-111111111111"
_INTERACTION_ID = "22222222-2222-4222-8222-222222222222"
_FEEDBACK_ID = "33333333-3333-4333-8333-333333333333"


class FakeAnswerService:
    async def answer(
        self,
        question: str,
        *,
        history: list[ConversationTurn] | None = None,
    ) -> GroundedAnswer:
        assert history == []
        with observe_stage("retrieval", "sdk"):
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
    async def answer(
        self,
        _question: str,
        *,
        history: list[ConversationTurn] | None = None,
    ) -> GroundedAnswer:
        assert history == []
        record_trace_metadata("intent", "sdk")
        record_trace_metadata("model", "test-model")
        record_trace_metadata("route", {"intent": "sdk"})
        record_trace_metadata("evidence_count", 2)
        record_trace_metadata("citations", [{"citation_id": "S1"}])
        with observe_stage("generation", "sdk"):
            raise LLMGenerationError("provider failed")


class FakeConversationStore:
    def __init__(self) -> None:
        self.answer_kwargs: dict[str, object] | None = None
        self.failure_kwargs: dict[str, object] | None = None
        self.feedback_kwargs: dict[str, object] | None = None
        self.feedback_exists = True

    async def assert_conversation_access(self, **_kwargs) -> bool:
        return True

    async def load_history(self, **_kwargs) -> list[ConversationTurn]:
        return []

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
        self.feedback_kwargs = kwargs
        if not self.feedback_exists:
            return None
        return FeedbackRecord(
            feedback_id=_FEEDBACK_ID,
            interaction_id=str(kwargs["interaction_id"]),
            rating=str(kwargs["rating"]),
            reason=kwargs.get("reason"),
            comment=kwargs.get("comment"),
        )


class FakeQualityStore:
    def __init__(self) -> None:
        self.reviews: list[tuple[str, str]] = []

    async def ensure_review(self, *, interaction_id: str, trigger: str) -> str:
        self.reviews.append((interaction_id, trigger))
        return "44444444-4444-4444-8444-444444444444"


def _app(service) -> tuple[FastAPI, FakeConversationStore]:
    app = FastAPI()
    store = FakeConversationStore()
    app.state.answer_service = service
    app.state.conversation_store = store
    app.state.quality_store = FakeQualityStore()
    app.include_router(ask_router)
    app.include_router(feedback_router)
    app.middleware("http")(observe_http_request)
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
    assert store.answer_kwargs["owner_user_id"] is None
    assert store.answer_kwargs["request_id"] == response.headers["X-Request-ID"]
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
    assert store.failure_kwargs["owner_user_id"] is None
    assert store.failure_kwargs["request_id"] == response.headers["X-Request-ID"]
    assert store.failure_kwargs["error_type"] == "LLMGenerationError"
    assert store.failure_kwargs["intent"] == "sdk"
    assert store.failure_kwargs["model"] == "test-model"
    assert store.failure_kwargs["evidence_count"] == 2
    assert store.failure_kwargs["route_json"] == {"intent": "sdk"}
    assert app.state.quality_store.reviews == [(_INTERACTION_ID, "failure")]
    durations = store.failure_kwargs["stage_durations"]
    assert isinstance(durations, dict)
    assert "generation" in durations


def test_feedback_endpoint_upserts_completed_interaction_feedback() -> None:
    app, store = _app(FakeAnswerService())

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
    assert store.feedback_kwargs is not None
    assert store.feedback_kwargs["actor_user_id"] is None
    assert app.state.quality_store.reviews == [(_INTERACTION_ID, "feedback_down")]


def test_feedback_rejects_unknown_interaction() -> None:
    app, store = _app(FakeAnswerService())
    store.feedback_exists = False

    response = TestClient(app).post(
        "/v1/feedback",
        json={"interaction_id": _INTERACTION_ID, "rating": "up"},
    )

    assert response.status_code == 404
