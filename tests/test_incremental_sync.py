import pytest

from app.ingestion.incremental import IncrementalPlan
from app.ingestion.models import SourceFile
from app.ingestion.sync import IncrementalSourceSync


class FakeStore:
    def __init__(self) -> None:
        self.snapshot_updates = []
        self.path_deletes = []
        self.stale_cleanup = []

    async def update_source_snapshot(self, **kwargs) -> None:
        self.snapshot_updates.append(kwargs)

    async def delete_source_paths(self, **kwargs) -> None:
        self.path_deletes.append(kwargs)

    async def remove_stale_source_versions(self, source_id: str, commit_sha: str) -> None:
        self.stale_cleanup.append((source_id, commit_sha))


class FakeRetrieval:
    def __init__(self) -> None:
        self.store = FakeStore()


@pytest.mark.asyncio
async def test_snapshot_application_updates_unchanged_and_removes_old_modified_chunks() -> None:
    retrieval = FakeRetrieval()
    service = IncrementalSourceSync(
        pipeline=object(),  # type: ignore[arg-type]
        retrieval=retrieval,  # type: ignore[arg-type]
        state=object(),  # type: ignore[arg-type]
    )
    plan = IncrementalPlan(
        added=(SourceFile(path="added.py", sha="a", content_type="code"),),
        modified=(SourceFile(path="changed.py", sha="b", content_type="code"),),
        deleted_paths=("deleted.py",),
        unchanged=(SourceFile(path="same.py", sha="c", content_type="code"),),
    )

    await service._apply_qdrant_snapshot(
        manifest_source_id="tractusx-sdk",
        version_ref="main",
        snapshot_commit_sha="new-commit",
        previous_snapshot_commit_sha="old-commit",
        plan=plan,
    )

    assert retrieval.store.snapshot_updates == [
        {
            "source_id": "tractusx-sdk",
            "paths": ["same.py"],
            "version_ref": "main",
            "snapshot_commit_sha": "new-commit",
        }
    ]
    assert retrieval.store.path_deletes == [
        {
            "source_id": "tractusx-sdk",
            "paths": ["changed.py"],
            "keep_snapshot_commit_sha": "new-commit",
        },
        {
            "source_id": "tractusx-sdk",
            "paths": ("deleted.py",),
        },
    ]
    assert retrieval.store.stale_cleanup == []


@pytest.mark.asyncio
async def test_first_managed_snapshot_cleans_untracked_stale_chunks() -> None:
    retrieval = FakeRetrieval()
    service = IncrementalSourceSync(
        pipeline=object(),  # type: ignore[arg-type]
        retrieval=retrieval,  # type: ignore[arg-type]
        state=object(),  # type: ignore[arg-type]
    )
    plan = IncrementalPlan(
        added=(SourceFile(path="first.py", sha="a", content_type="code"),),
        modified=(),
        deleted_paths=(),
        unchanged=(),
    )

    await service._apply_qdrant_snapshot(
        manifest_source_id="tractusx-sdk",
        version_ref="main",
        snapshot_commit_sha="first-commit",
        previous_snapshot_commit_sha=None,
        plan=plan,
    )

    assert retrieval.store.stale_cleanup == [("tractusx-sdk", "first-commit")]
