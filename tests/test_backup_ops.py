from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import ops_auth
from app.api.routes import backup_ops
from app.core.config import Settings


def _app(monkeypatch) -> FastAPI:
    monkeypatch.setattr(
        ops_auth,
        "get_settings",
        lambda: Settings(ops_admin_key="secret"),
    )
    monkeypatch.setattr(
        backup_ops,
        "get_settings",
        lambda: Settings(ops_admin_key="secret"),
    )
    app = FastAPI()
    app.include_router(backup_ops.router)
    return app


def _headers() -> dict[str, str]:
    return {"X-TractusMind-Admin-Key": "secret"}


def test_backup_requires_admin_authentication(monkeypatch) -> None:
    response = TestClient(_app(monkeypatch)).post("/v1/ops/backup")

    assert response.status_code == 401


def test_admin_can_download_full_backup(monkeypatch) -> None:
    async def fake_build(_settings: Settings, workdir: Path) -> Path:
        archive = workdir / "tractusmind-backup-test.zip"
        archive.write_bytes(b"backup-archive")
        return archive

    monkeypatch.setattr(backup_ops, "build_backup_archive", fake_build)

    response = TestClient(_app(monkeypatch)).post(
        "/v1/ops/backup",
        headers=_headers(),
    )

    assert response.status_code == 200
    assert response.content == b"backup-archive"
    assert response.headers["content-type"] == "application/zip"
    assert "tractusmind-backup-test.zip" in response.headers["content-disposition"]
    assert response.headers["x-tractusmind-backup"] == "postgresql,qdrant,source-registry"


def test_postgres_environment_uses_url_without_exporting_dsn() -> None:
    settings = Settings(
        database_url=(
            "postgresql+asyncpg://backup_user:backup_password@postgres.internal:5433/"
            "tractusmind?sslmode=require"
        )
    )

    env, database = backup_ops._postgres_environment(settings)

    assert database == "tractusmind"
    assert env["PGHOST"] == "postgres.internal"
    assert env["PGPORT"] == "5433"
    assert env["PGUSER"] == "backup_user"
    assert env["PGPASSWORD"] == "backup_password"
    assert env["PGSSLMODE"] == "require"


async def test_qdrant_backup_uses_full_storage_snapshot(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "POST" and request.url.path == "/snapshots":
            return httpx.Response(
                200,
                json={"result": {"name": "full-storage.snapshot"}},
            )
        if request.method == "GET" and request.url.path == "/snapshots/full-storage.snapshot":
            return httpx.Response(200, content=b"qdrant-full-storage")
        if request.method == "DELETE" and request.url.path == "/snapshots/full-storage.snapshot":
            return httpx.Response(200, json={"result": True})
        return httpx.Response(404, json={"status": {"error": "unexpected route"}})

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def client_factory(**kwargs):
        return real_async_client(transport=transport, **kwargs)

    monkeypatch.setattr(backup_ops.httpx, "AsyncClient", client_factory)

    snapshot = await backup_ops._snapshot_qdrant(
        Settings(qdrant_url="http://qdrant.test"),
        tmp_path,
    )

    assert snapshot.read_bytes() == b"qdrant-full-storage"
    assert calls == [
        ("POST", "/snapshots"),
        ("GET", "/snapshots/full-storage.snapshot"),
        ("DELETE", "/snapshots/full-storage.snapshot"),
    ]
