from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import ops_auth
from app.api.routes import ops
from app.core.config import Settings
from app.ingestion.models import SourceDefinition, SourcePriority
from app.state.store import IngestionRunRecord, SourceStatusRecord


class FakeRedis:
    async def exists(self, key: str) -> int:
        return int(key.endswith("source-a"))

    async def ping(self) -> bool:
        return True


class FakeStore:
    async def ensure_schema(self) -> None:
        return None

    async def list_source_statuses(self) -> list[SourceStatusRecord]:
        return [
            SourceStatusRecord(
                source_id="source-a",
                repository="eclipse-tractusx/source-a",
                component="sdk",
                version_ref="main",
                snapshot_commit_sha="a" * 40,
                last_successful_run_id="run-1",
                updated_at=datetime(2026, 8, 20, tzinfo=UTC),
                file_count=42,
            )
        ]

    async def run_status_counts(self) -> dict[str, int]:
        return {"succeeded": 3, "failed": 1}

    async def list_runs(self, **_kwargs) -> list[IngestionRunRecord]:
        return [_run()]

    async def get_run(self, run_id: str) -> IngestionRunRecord | None:
        return _run() if run_id == "run-1" else None


class FakeMessage:
    message_id = "message-1"


class FakeActor:
    def send(self, source_id: str) -> FakeMessage:
        assert source_id == "source-a"
        return FakeMessage()


def _source() -> SourceDefinition:
    return SourceDefinition(
        id="source-a",
        owner="eclipse-tractusx",
        repo="source-a",
        component="sdk",
        priority=SourcePriority.HIGH,
    )


def _run() -> IngestionRunRecord:
    return IngestionRunRecord(
        run_id="run-1",
        source_id="source-a",
        repository="eclipse-tractusx/source-a",
        requested_ref="main",
        snapshot_commit_sha="a" * 40,
        status="succeeded",
        discovered_count=42,
        added_count=1,
        modified_count=2,
        deleted_count=0,
        unchanged_count=39,
        fetched_count=3,
        chunk_count=10,
        indexed_count=10,
        error_message=None,
        started_at=datetime(2026, 8, 20, tzinfo=UTC),
        finished_at=datetime(2026, 8, 20, 0, 1, tzinfo=UTC),
    )


def _app() -> FastAPI:
    app = FastAPI()
    app.state.postgres = object()
    app.state.redis = FakeRedis()
    app.include_router(ops.router)
    return app


def test_ops_are_disabled_without_admin_key(monkeypatch) -> None:
    monkeypatch.setattr(ops_auth, "get_settings", lambda: Settings(ops_admin_key=None))

    response = TestClient(_app()).get("/v1/ops/sources")

    assert response.status_code == 503


def test_ops_sources_expose_snapshot_and_lock_state(monkeypatch) -> None:
    monkeypatch.setattr(
        ops_auth,
        "get_settings",
        lambda: Settings(ops_admin_key="secret"),
    )
    monkeypatch.setattr(ops, "SourceStateStore", lambda _engine: FakeStore())
    monkeypatch.setattr(ops, "load_source_registry", lambda: [_source()])

    response = TestClient(_app()).get(
        "/v1/ops/sources",
        headers={"X-TractusMind-Admin-Key": "secret"},
    )

    assert response.status_code == 200
    payload = response.json()[0]
    assert payload["source_id"] == "source-a"
    assert payload["snapshot_commit_sha"] == "a" * 40
    assert payload["file_count"] == 42
    assert payload["locked"] is True


def test_ops_enqueue_returns_dramatiq_message_id(monkeypatch) -> None:
    monkeypatch.setattr(
        ops_auth,
        "get_settings",
        lambda: Settings(ops_admin_key="secret"),
    )
    monkeypatch.setattr(ops, "get_source", lambda _source_id: _source())
    monkeypatch.setattr(ops, "sync_source_task", FakeActor())

    response = TestClient(_app()).post(
        "/v1/ops/sources/source-a/sync",
        headers={"X-TractusMind-Admin-Key": "secret"},
    )

    assert response.status_code == 202
    assert response.json() == {
        "source_id": "source-a",
        "status": "queued",
        "message_id": "message-1",
    }
