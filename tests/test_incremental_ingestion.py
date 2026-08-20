from app.ingestion.incremental import build_incremental_plan
from app.ingestion.models import SourceFile, SourceManifest
from app.state.store import StoredSourceFile


def _file(path: str, sha: str) -> SourceFile:
    return SourceFile(
        path=path,
        sha=sha,
        size=10,
        content_type="code",
    )


def _stored(path: str, sha: str) -> StoredSourceFile:
    return StoredSourceFile(
        path=path,
        blob_sha=sha,
        content_commit_sha="old-commit",
        size_bytes=10,
        content_type="code",
    )


def test_incremental_plan_uses_blob_sha_without_fetching_content() -> None:
    manifest = SourceManifest(
        source_id="tractusx-sdk",
        repository="eclipse-tractusx/tractusx-sdk",
        component="sdk",
        requested_ref="main",
        commit_sha="new-commit",
        archived=False,
        files=[
            _file("added.py", "sha-added"),
            _file("modified.py", "sha-new"),
            _file("unchanged.py", "sha-same"),
        ],
    )
    previous = {
        "modified.py": _stored("modified.py", "sha-old"),
        "unchanged.py": _stored("unchanged.py", "sha-same"),
        "deleted.py": _stored("deleted.py", "sha-deleted"),
    }

    plan = build_incremental_plan(manifest, previous)

    assert [item.path for item in plan.added] == ["added.py"]
    assert [item.path for item in plan.modified] == ["modified.py"]
    assert [item.path for item in plan.unchanged] == ["unchanged.py"]
    assert plan.deleted_paths == ("deleted.py",)
    assert [item.path for item in plan.changed_files] == ["added.py", "modified.py"]
    assert plan.has_content_changes is True


def test_incremental_plan_reports_no_content_change() -> None:
    manifest = SourceManifest(
        source_id="tractusx-sdk",
        repository="eclipse-tractusx/tractusx-sdk",
        component="sdk",
        requested_ref="main",
        commit_sha="new-commit",
        archived=False,
        files=[_file("same.py", "same-sha")],
    )
    previous = {"same.py": _stored("same.py", "same-sha")}

    plan = build_incremental_plan(manifest, previous)

    assert plan.changed_files == ()
    assert plan.deleted_paths == ()
    assert plan.has_content_changes is False
