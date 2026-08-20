import app.main as main_module

from fastapi.testclient import TestClient

from app.db import CURRENT_DATABASE_REVISION


async def _current_database(_engine) -> str:
    return CURRENT_DATABASE_REVISION


def test_liveness(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "verify_database_revision",
        _current_database,
    )
    with TestClient(main_module.app) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "verify_database_revision",
        _current_database,
    )
    with TestClient(main_module.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.json()["name"] == "TractusMind"
