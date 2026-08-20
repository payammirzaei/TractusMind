from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.security import RequestProtectionMiddleware


def _protected_app(*, max_body: int = 1024, rate_limit: int = 10) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        RequestProtectionMiddleware,
        max_body_bytes=max_body,
        max_concurrent_requests=2,
        rate_limit_requests=rate_limit,
        rate_limit_window_seconds=60,
        trust_forwarded_for=True,
    )

    @app.post("/echo")
    async def echo(payload: dict[str, str]) -> dict[str, str]:
        return payload

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        return {"status": "ok"}

    return app


def test_security_headers_are_added() -> None:
    response = TestClient(_protected_app()).get("/ok")

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_oversized_request_is_rejected_before_handler() -> None:
    response = TestClient(_protected_app(max_body=32)).post(
        "/echo",
        content=b"x" * 64,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413


def test_rate_limit_returns_retry_after() -> None:
    client = TestClient(_protected_app(rate_limit=2))
    headers = {"X-Forwarded-For": "203.0.113.10"}

    assert client.get("/ok", headers=headers).status_code == 200
    assert client.get("/ok", headers=headers).status_code == 200
    limited = client.get("/ok", headers=headers)

    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) >= 1


def test_settings_load_secret_file_with_precedence(tmp_path: Path) -> None:
    secret = tmp_path / "ops-key"
    secret.write_text("file-secret\n", encoding="utf-8")

    settings = Settings(
        ops_admin_key="plaintext-value",
        ops_admin_key_file=str(secret),
    )

    assert settings.ops_admin_key == "file-secret"


def test_settings_parse_trusted_hosts_and_cors() -> None:
    settings = Settings(
        trusted_hosts="api.example.com, api, localhost",
        cors_origins="https://ui.example.com, https://admin.example.com",
    )

    assert settings.trusted_host_list == ["api.example.com", "api", "localhost"]
    assert settings.cors_origin_list == [
        "https://ui.example.com",
        "https://admin.example.com",
    ]


def test_oidc_rejects_symmetric_signing_algorithms() -> None:
    with pytest.raises(ValueError, match="asymmetric signing only"):
        Settings(
            oidc_enabled=True,
            oidc_issuer_url="https://id.example.com/realms/tractusmind",
            oidc_allowed_algorithms="HS256",
        )
