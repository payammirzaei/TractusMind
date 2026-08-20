from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import ops_auth
from app.api.routes import interaction_ops
from app.conversations.store import InteractionRecord
from app.core.config import Settings

_INTERACTION_ID = "22222222-2222-4222-8222-222222222222"


def _record() -> InteractionRecord:
    return InteractionRecord(
        interaction_id=_INTERACTION_ID,
        conversation_id="11111111-1111-4111-8111-111111111111",
        question="How do I use the SDK?",
        answer="Use the SDK evidence [S1].",
        status="completed",
        grounded=True,
        abstained=False,
        evidence_count=1,
        model="test-model",
        intent="sdk",
        route_json={"intent": "sdk"},
        citations_json=[{"citation_id": "S1"}],
        verification_json={"passed": True},
        stage_durations_json={"retrieval": 0.1, "generation": 0.2},
        total_duration_seconds=0.4,
        trace_id="a" * 32,
        error_type=None,
        created_at=datetime(2026, 8, 20, tzinfo=UTC),
        feedback_rating="up",
        feedback_reason="correct",
        feedback_comment=None,
    )


class FakeConversationStore:
    async def list_interactions(self, **_kwargs) -> list[InteractionRecord]:
        return [_record()]

    async def get_interaction(self, interaction_id: str) -> InteractionRecord | None:
        return _record() if interaction_id == _INTERACTION_ID else None

    async def feedback_counts(self) -> dict[str, int]:
        return {"up": 3, "down": 1}


def _app() -> FastAPI:
    app = FastAPI()
    app.state.conversation_store = FakeConversationStore()
    app.include_router(interaction_ops.router)
    return app


def _authorize(monkeypatch) -> None:
    monkeypatch.setattr(
        ops_auth,
        "get_settings",
        lambda: Settings(ops_admin_key="secret"),
    )


def test_admin_can_inspect_persisted_interactions(monkeypatch) -> None:
    _authorize(monkeypatch)

    response = TestClient(_app()).get(
        "/v1/ops/interactions",
        headers={"X-TractusMind-Admin-Key": "secret"},
    )

    assert response.status_code == 200
    payload = response.json()[0]
    assert payload["interaction_id"] == _INTERACTION_ID
    assert payload["stage_durations"]["retrieval"] == 0.1
    assert payload["feedback_rating"] == "up"


def test_admin_can_open_one_interaction_trace(monkeypatch) -> None:
    _authorize(monkeypatch)

    response = TestClient(_app()).get(
        f"/v1/ops/interactions/{_INTERACTION_ID}",
        headers={"X-TractusMind-Admin-Key": "secret"},
    )

    assert response.status_code == 200
    assert response.json()["trace_id"] == "a" * 32


def test_admin_can_read_feedback_summary(monkeypatch) -> None:
    _authorize(monkeypatch)

    response = TestClient(_app()).get(
        "/v1/ops/feedback/summary",
        headers={"X-TractusMind-Admin-Key": "secret"},
    )

    assert response.status_code == 200
    assert response.json() == {"counts": {"up": 3, "down": 1}}
