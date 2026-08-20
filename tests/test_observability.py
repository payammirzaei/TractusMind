from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import metrics as metrics_route
from app.core.config import Settings
from app.observability.http import observe_http_request


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(metrics_route.router)
    app.middleware("http")(observe_http_request)

    @app.get("/items/{item_id}")
    async def item(item_id: str) -> dict[str, str]:
        return {"item_id": item_id}

    return app


def test_metrics_are_available_in_development(monkeypatch) -> None:
    monkeypatch.setattr(
        metrics_route,
        "get_settings",
        lambda: Settings(app_env="development", metrics_enabled=True),
    )

    response = TestClient(_app()).get("/metrics")

    assert response.status_code == 200
    assert "tractusmind_http_requests_total" in response.text
    assert "tractusmind_quality_review_signals_total" in response.text
    assert "tractusmind_quality_review_decisions_total" in response.text
    assert "tractusmind_quality_regression_promotions_total" in response.text


def test_metrics_require_key_outside_development(monkeypatch) -> None:
    monkeypatch.setattr(
        metrics_route,
        "get_settings",
        lambda: Settings(
            app_env="production",
            metrics_enabled=True,
            metrics_admin_key="metrics-secret",
        ),
    )
    client = TestClient(_app())

    denied = client.get("/metrics")
    allowed = client.get(
        "/metrics",
        headers={"X-TractusMind-Metrics-Key": "metrics-secret"},
    )

    assert denied.status_code == 401
    assert allowed.status_code == 200


def test_http_middleware_adds_request_id_header() -> None:
    response = TestClient(_app()).get("/items/abc")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"]
