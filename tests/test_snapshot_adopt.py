from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes import snapshot_adopt
from app.ingestion.models import SourceDefinition, SourcePriority


class FakeRedis:
    def __init__(self, locked: bool = False) -> None:
        self.locked = locked

    async def exists(self, _key: str) -> int:
        return int(self.locked)


class FakeStore:
    def __init__(self) -> None:
        self.completed: dict[str, object] | None = None

    async def ensure_schema(self) -> None:
        return None

    async def load_file_states(self, _source_id: str) -> dict[str, object]:
        return {}

    async def start_run(self, _manifest) -> str:
        return "external-run"

    async def complete_run(self, **kwargs) -> None:
        self.completed = kwargs

    async def fail_run(self, _run_id: str, _error: Exception | str) -> None:
        raise AssertionError("happy-path adoption must not fail")


def _source() -> SourceDefinition:
    return SourceDefinition(
        id="tractusx-docs",
        owner="eclipse-tractusx",
        repo="eclipse-tractusx.github.io",
        component="documentation",
        priority=SourcePriority.HIGH,
        ref="main",
    )


def _request(redis: FakeRedis | None = None):
    state = SimpleNamespace(redis=redis or FakeRedis(), postgres=object())
    return SimpleNamespace(app=SimpleNamespace(state=state))


@pytest.mark.asyncio
async def test_adopt_snapshot_marks_fully_indexed_external_snapshot_succeeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeStore()
    monkeypatch.setattr(snapshot_adopt, "get_source", lambda _source_id: _source())
    monkeypatch.setattr(snapshot_adopt, "SourceStateStore", lambda _engine: store)

    payload = snapshot_adopt.AdoptSnapshotRequest(
        version_ref="main",
        snapshot_commit_sha="a" * 40,
        files=[
            snapshot_adopt.AdoptedFile(
                path="docs/intro.md",
                blob_sha="b" * 40,
                size_bytes=123,
                content_type="markdown",
            )
        ],
        chunk_count=12,
        indexed_count=12,
    )

    response = await snapshot_adopt.adopt_snapshot(
        "tractusx-docs",
        payload,
        _request(),  # type: ignore[arg-type]
    )

    assert response.status == "succeeded"
    assert response.run_id == "external-run"
    assert response.file_count == 1
    assert store.completed is not None
    assert store.completed["chunk_count"] == 12
    assert store.completed["indexed_count"] == 12


@pytest.mark.asyncio
async def test_adopt_snapshot_rejects_partial_vector_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(snapshot_adopt, "get_source", lambda _source_id: _source())
    payload = snapshot_adopt.AdoptSnapshotRequest(
        version_ref="main",
        snapshot_commit_sha="a" * 40,
        files=[],
        chunk_count=12,
        indexed_count=11,
    )

    with pytest.raises(HTTPException) as exc:
        await snapshot_adopt.adopt_snapshot(
            "tractusx-docs",
            payload,
            _request(),  # type: ignore[arg-type]
        )

    assert exc.value.status_code == 409
