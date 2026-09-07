from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.activity import ActivityRecord
from app.api import ops_auth
from app.api.routes import activity
from app.core.config import Settings


class FakeActivityStore:
    def __init__(self) -> None:
        self.recorded: list[dict[str, object]] = []

    async def record_event(self, **kwargs) -> str:
        self.recorded.append(kwargs)
        return "33333333-3333-4333-8333-333333333333"

    async def list_events(self, **_kwargs) -> list[ActivityRecord]:
        return [
            ActivityRecord(
                event_id="33333333-3333-4333-8333-333333333333",
                event_type="page_view",
                user_id=None,
                session_id="session-1",
                visitor_id="visitor-1",
                request_id="request-1",
                ip_address="127.0.0.1",
                method=None,
                path="/overview",
                status_code=None,
                duration_ms=None,
                referrer=None,
                user_agent="test-agent",
                target=None,
                metadata_json={"title": "TractusMind"},
                created_at=datetime(2026, 9, 7, tzinfo=UTC),
            )
        ]


def _app() -> tuple[FastAPI, FakeActivityStore]:
    app = FastAPI()
    store = FakeActivityStore()
    app.state.activity_store = store
    app.include_router(activity.router)
    app.include_router(activity.ops_router)
    return app, store


def test_anonymous_page_view_is_accepted() -> None:
    app, store = _app()

    response = TestClient(app).post(
        "/v1/activity/events",
        json={
            "event_type": "page_view",
            "session_id": "session-1",
            "visitor_id": "visitor-1",
            "path": "/overview",
            "metadata": {"title": "TractusMind"},
        },
        headers={"user-agent": "test-agent"},
    )

    assert response.status_code == 202
    assert response.json() == {"accepted": True}
    assert store.recorded[0]["event_type"] == "page_view"
    assert store.recorded[0]["path"] == "/overview"
    assert store.recorded[0]["user_agent"] == "test-agent"


def test_client_cannot_spoof_http_request_event() -> None:
    app, _store = _app()

    response = TestClient(app).post(
        "/v1/activity/events",
        json={
            "event_type": "http_request",
            "session_id": "session-1",
            "visitor_id": "visitor-1",
            "path": "/v1/ask",
        },
    )

    assert response.status_code == 422


def test_operator_can_read_activity(monkeypatch) -> None:
    app, _store = _app()
    monkeypatch.setattr(
        ops_auth,
        "get_settings",
        lambda: Settings(ops_admin_key="secret"),
    )

    response = TestClient(app).get(
        "/v1/ops/activity",
        headers={"X-TractusMind-Admin-Key": "secret"},
    )

    assert response.status_code == 200
    payload = response.json()[0]
    assert payload["event_type"] == "page_view"
    assert payload["visitor_id"] == "visitor-1"
    assert payload["metadata"]["title"] == "TractusMind"
