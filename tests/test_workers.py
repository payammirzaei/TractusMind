import pytest

from app.core.config import Settings
from app.ingestion.models import SourceDefinition, SourcePriority
from app.workers import scheduler
from app.workers import sync as worker_sync
from app.workers.tasks import SOURCE_SYNC_TIME_LIMIT_MS, sync_source_task


class FakeMessage:
    def __init__(self, message_id: str) -> None:
        self.message_id = message_id


class FakeActor:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(self, source_id: str) -> FakeMessage:
        self.sent.append(source_id)
        return FakeMessage(f"message-{source_id}")


class FakeLock:
    def __init__(self, acquired: bool) -> None:
        self.acquired = acquired
        self.released = False

    async def acquire(self, *, blocking: bool) -> bool:
        assert blocking is False
        return self.acquired

    async def release(self) -> None:
        self.released = True


class FakeRedis:
    def __init__(self, acquired: bool) -> None:
        self.lock_instance = FakeLock(acquired)
        self.closed = False
        self.lock_calls: list[dict[str, object]] = []

    def lock(self, name: str, *, timeout: int, blocking: bool) -> FakeLock:
        self.lock_calls.append(
            {
                "name": name,
                "timeout": timeout,
                "blocking": blocking,
            }
        )
        return self.lock_instance

    async def aclose(self) -> None:
        self.closed = True


def _source(source_id: str) -> SourceDefinition:
    return SourceDefinition(
        id=source_id,
        owner="eclipse-tractusx",
        repo=source_id,
        component="test",
        priority=SourcePriority.HIGH,
    )


def test_source_sync_actor_has_full_corpus_time_budget() -> None:
    assert SOURCE_SYNC_TIME_LIMIT_MS == 14_400_000
    assert sync_source_task.options["time_limit"] == SOURCE_SYNC_TIME_LIMIT_MS


def test_scheduler_enqueues_each_enabled_source(monkeypatch: pytest.MonkeyPatch) -> None:
    actor = FakeActor()
    monkeypatch.setattr(scheduler, "sync_source_task", actor)

    source_ids = scheduler.enqueue_sources([_source("source-a"), _source("source-b")])

    assert source_ids == ["source-a", "source-b"]
    assert actor.sent == source_ids


@pytest.mark.asyncio
async def test_worker_skips_source_when_distributed_lock_is_busy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis(acquired=False)
    monkeypatch.setattr(worker_sync, "get_source", lambda _source_id: object())
    monkeypatch.setattr(worker_sync, "create_redis_client", lambda _settings: redis)

    result = await worker_sync.run_source_sync(
        "tractusx-sdk",
        settings=Settings(source_sync_lock_seconds=600),
    )

    assert result == {"status": "locked", "source_id": "tractusx-sdk"}
    assert redis.closed is True
    assert redis.lock_instance.released is False
    assert redis.lock_calls[0]["name"] == "tractusmind:source-sync:tractusx-sdk"


@pytest.mark.asyncio
async def test_worker_releases_lock_when_resource_setup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis(acquired=True)
    monkeypatch.setattr(worker_sync, "get_source", lambda _source_id: object())
    monkeypatch.setattr(worker_sync, "create_redis_client", lambda _settings: redis)

    def fail_engine(_settings: Settings):
        raise RuntimeError("postgres unavailable")

    monkeypatch.setattr(worker_sync, "create_postgres_engine", fail_engine)

    with pytest.raises(RuntimeError, match="postgres unavailable"):
        await worker_sync.run_source_sync(
            "tractusx-sdk",
            settings=Settings(source_sync_lock_seconds=600),
        )

    assert redis.lock_instance.released is True
    assert redis.closed is True
