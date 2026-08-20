from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import ops_auth
from app.api.routes import user_ops
from app.auth.store import UserCredential, UserIdentity
from app.core.config import Settings

_USER_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


class FakeAuthStore:
    async def list_users(self, limit: int = 200) -> list[UserIdentity]:
        assert limit == 200
        return [self._identity()]

    async def create_user(self, display_name: str) -> UserCredential:
        assert display_name == "Alice"
        return UserCredential(user=self._identity(), api_key="tm_created")

    async def rotate_api_key(self, user_id: str) -> UserCredential | None:
        if user_id != _USER_ID:
            return None
        return UserCredential(user=self._identity(), api_key="tm_rotated")

    async def set_enabled(self, user_id: str, enabled: bool) -> UserIdentity | None:
        if user_id != _USER_ID:
            return None
        return UserIdentity(
            user_id=_USER_ID,
            display_name="Alice",
            api_key_prefix="tm_prefix",
            enabled=enabled,
        )

    @staticmethod
    def _identity() -> UserIdentity:
        return UserIdentity(
            user_id=_USER_ID,
            display_name="Alice",
            api_key_prefix="tm_prefix",
            enabled=True,
        )


def _app(monkeypatch) -> FastAPI:
    monkeypatch.setattr(
        ops_auth,
        "get_settings",
        lambda: Settings(ops_admin_key="secret"),
    )
    app = FastAPI()
    app.state.auth_store = FakeAuthStore()
    app.include_router(user_ops.router)
    return app


def _headers() -> dict[str, str]:
    return {"X-TractusMind-Admin-Key": "secret"}


def test_admin_creates_user_and_receives_key_once(monkeypatch) -> None:
    response = TestClient(_app(monkeypatch)).post(
        "/v1/ops/users",
        headers=_headers(),
        json={"display_name": "Alice"},
    )

    assert response.status_code == 200
    assert response.json()["user_id"] == _USER_ID
    assert response.json()["api_key"] == "tm_created"


def test_admin_rotation_returns_replacement_key(monkeypatch) -> None:
    response = TestClient(_app(monkeypatch)).post(
        f"/v1/ops/users/{_USER_ID}/rotate",
        headers=_headers(),
    )

    assert response.status_code == 200
    assert response.json()["api_key"] == "tm_rotated"


def test_admin_can_disable_user(monkeypatch) -> None:
    response = TestClient(_app(monkeypatch)).patch(
        f"/v1/ops/users/{_USER_ID}",
        headers=_headers(),
        json={"enabled": False},
    )

    assert response.status_code == 200
    assert response.json()["enabled"] is False
