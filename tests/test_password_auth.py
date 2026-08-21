from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import auth as password_auth
from app.auth.store import UserIdentity, UserRole
from app.core.config import Settings

_USER = UserIdentity(
    user_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    display_name="Payam",
    api_key_prefix=None,
    enabled=True,
    role=UserRole.ADMIN,
    auth_type="password",
    username="payam",
)


class FakeAuthStore:
    async def authenticate_password(self, username: str, password: str) -> UserIdentity | None:
        if username.casefold() == "payam" and password == "correct horse battery staple":
            return _USER
        return None

    @staticmethod
    def issue_session(
        identity: UserIdentity,
        *,
        signing_key: str,
        ttl_seconds: int,
    ) -> str:
        assert identity == _USER
        assert signing_key == "s" * 64
        assert ttl_seconds == 3600
        return "tm_session.signed"


def _app(monkeypatch, *, signing_key: str | None = "s" * 64) -> FastAPI:
    monkeypatch.setattr(
        password_auth,
        "get_settings",
        lambda: Settings(session_signing_key=signing_key, session_ttl_seconds=3600),
    )
    app = FastAPI()
    app.state.auth_store = FakeAuthStore()
    app.include_router(password_auth.router)
    return app


def test_password_login_returns_short_lived_backend_session(monkeypatch) -> None:
    response = TestClient(_app(monkeypatch)).post(
        "/v1/auth/login",
        json={"username": "Payam", "password": "correct horse battery staple"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "token": "tm_session.signed",
        "user_id": _USER.user_id,
        "display_name": "Payam",
        "username": "payam",
        "role": "admin",
        "auth_type": "password",
        "expires_in": 3600,
    }


def test_password_login_rejects_bad_credentials_without_user_detail(monkeypatch) -> None:
    response = TestClient(_app(monkeypatch)).post(
        "/v1/auth/login",
        json={"username": "payam", "password": "wrong"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"


def test_password_login_fails_closed_without_session_signing_key(monkeypatch) -> None:
    response = TestClient(_app(monkeypatch, signing_key=None)).post(
        "/v1/auth/login",
        json={"username": "payam", "password": "correct horse battery staple"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Local sign-in is not configured"
