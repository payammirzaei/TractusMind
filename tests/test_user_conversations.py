from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.ask import router as ask_router
from app.api.routes.conversations import router as conversations_router
from app.auth.store import UserIdentity
from app.conversations.history import ConversationTurn
from app.conversations.store import (
    ConversationAccessError,
    ConversationRecord,
    InteractionIdentity,
)
from app.generation.models import GroundedAnswer
from app.routing.models import QueryIntent, QueryRoute

_USER_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
_CONVERSATION_ID = "11111111-1111-4111-8111-111111111111"
_INTERACTION_ID = "22222222-2222-4222-8222-222222222222"


class FakeAuthStore:
    async def authenticate(self, api_key: str) -> UserIdentity | None:
        if api_key != "tm_valid":
            return None
        return UserIdentity(
            user_id=_USER_ID,
            display_name="Test User",
            api_key_prefix="tm_valid",
            enabled=True,
        )


class FakeAnswerService:
    def __init__(self) -> None:
        self.history: list[ConversationTurn] | None = None

    async def answer(
        self,
        question: str,
        *,
        history: list[ConversationTurn] | None = None,
    ) -> GroundedAnswer:
        self.history = history
        return GroundedAnswer(
            question=question,
            answer="Use contract negotiation evidence [S1].",
            grounded=True,
            abstained=False,
            evidence_count=1,
            route=QueryRoute(intent=QueryIntent.SDK),
            model="test-model",
        )


class FakeConversationStore:
    def __init__(self) -> None:
        self.deny = False
        self.answer_kwargs: dict[str, object] | None = None

    async def assert_conversation_access(self, **kwargs) -> bool:
        if self.deny or kwargs["owner_user_id"] != _USER_ID:
            raise ConversationAccessError("conversation is not available")
        return True

    async def load_history(self, **kwargs) -> list[ConversationTurn]:
        assert kwargs["owner_user_id"] == _USER_ID
        return [
            ConversationTurn(
                question="How do I create an asset with the SDK?",
                answer="Use the SDK asset service [S1].",
            )
        ]

    async def record_answer(self, **kwargs) -> InteractionIdentity:
        self.answer_kwargs = kwargs
        return InteractionIdentity(
            interaction_id=_INTERACTION_ID,
            conversation_id=_CONVERSATION_ID,
        )

    async def list_owned_conversations(self, **kwargs) -> list[ConversationRecord]:
        assert kwargs["owner_user_id"] == _USER_ID
        now = datetime(2026, 8, 20, tzinfo=UTC)
        return [
            ConversationRecord(
                conversation_id=_CONVERSATION_ID,
                created_at=now,
                updated_at=now,
            )
        ]


class FakeQualityStore:
    async def ensure_review(self, **_kwargs) -> str:
        return "44444444-4444-4444-8444-444444444444"


def _app() -> tuple[FastAPI, FakeAnswerService, FakeConversationStore]:
    app = FastAPI()
    service = FakeAnswerService()
    store = FakeConversationStore()
    app.state.auth_store = FakeAuthStore()
    app.state.answer_service = service
    app.state.conversation_store = store
    app.state.quality_store = FakeQualityStore()
    app.include_router(ask_router)
    app.include_router(conversations_router)
    return app, service, store


def _headers(token: str = "tm_valid") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_authenticated_follow_up_loads_history_and_persists_owner() -> None:
    app, service, store = _app()

    response = TestClient(app).post(
        "/v1/ask",
        headers=_headers(),
        json={
            "question": "What about contract negotiation?",
            "conversation_id": _CONVERSATION_ID,
        },
    )

    assert response.status_code == 200
    assert service.history is not None
    assert service.history[0].question.startswith("How do I create")
    assert store.answer_kwargs is not None
    assert store.answer_kwargs["owner_user_id"] == _USER_ID


def test_invalid_bearer_token_is_rejected() -> None:
    app, _service, _store = _app()

    response = TestClient(app).post(
        "/v1/ask",
        headers=_headers("wrong"),
        json={"question": "How do I use the SDK?"},
    )

    assert response.status_code == 401


def test_cross_user_conversation_access_fails_closed() -> None:
    app, _service, store = _app()
    store.deny = True

    response = TestClient(app).post(
        "/v1/ask",
        headers=_headers(),
        json={
            "question": "What about contract negotiation?",
            "conversation_id": _CONVERSATION_ID,
        },
    )

    assert response.status_code == 404


def test_authenticated_user_can_list_only_owned_conversations() -> None:
    app, _service, _store = _app()

    response = TestClient(app).get(
        "/v1/conversations",
        headers=_headers(),
    )

    assert response.status_code == 200
    assert response.json()[0]["conversation_id"] == _CONVERSATION_ID
