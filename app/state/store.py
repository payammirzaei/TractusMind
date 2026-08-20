from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.ingestion.models import SourceManifest
from app.state.models import Base, IngestionRun, SourceFileState, SourceState


@dataclass(frozen=True)
class StoredSourceSnapshot:
    source_id: str
    version_ref: str
    snapshot_commit_sha: str


@dataclass(frozen=True)
class StoredSourceFile:
    path: str
    blob_sha: str
    content_commit_sha: str
    size_bytes: int
    content_type: str


class SourceStateStore:
    """Persist successful source snapshots and ingestion-run audit data."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self.sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def ensure_schema(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def load_source_snapshot(
        self,
        source_id: str,
    ) -> StoredSourceSnapshot | None:
        async with self.sessions() as session:
            row = await session.get(SourceState, source_id)
        if row is None:
            return None
        return StoredSourceSnapshot(
            source_id=row.source_id,
            version_ref=row.version_ref,
            snapshot_commit_sha=row.snapshot_commit_sha,
        )

    async def load_file_states(self, source_id: str) -> dict[str, StoredSourceFile]:
        async with self.sessions() as session:
            rows = (
                await session.scalars(
                    select(SourceFileState).where(SourceFileState.source_id == source_id)
                )
            ).all()
        return {
            row.path: StoredSourceFile(
                path=row.path,
                blob_sha=row.blob_sha,
                content_commit_sha=row.content_commit_sha,
                size_bytes=row.size_bytes,
                content_type=row.content_type,
            )
            for row in rows
        }

    async def start_run(self, manifest: SourceManifest) -> str:
        run = IngestionRun(
            source_id=manifest.source_id,
            repository=manifest.repository,
            requested_ref=manifest.requested_ref,
            snapshot_commit_sha=manifest.commit_sha,
            discovered_count=len(manifest.files),
        )
        async with self.sessions.begin() as session:
            session.add(run)
        return run.run_id

    async def complete_run(
        self,
        *,
        run_id: str,
        manifest: SourceManifest,
        added_paths: set[str],
        modified_paths: set[str],
        deleted_paths: set[str],
        unchanged_paths: set[str],
        fetched_count: int,
        chunk_count: int,
        indexed_count: int,
        previous_files: dict[str, StoredSourceFile],
    ) -> None:
        current_by_path = {source_file.path: source_file for source_file in manifest.files}
        changed_paths = added_paths | modified_paths

        async with self.sessions.begin() as session:
            source = await session.get(SourceState, manifest.source_id)
            if source is None:
                source = SourceState(
                    source_id=manifest.source_id,
                    repository=manifest.repository,
                    component=manifest.component,
                    version_ref=manifest.requested_ref,
                    snapshot_commit_sha=manifest.commit_sha,
                )
                session.add(source)
            else:
                source.repository = manifest.repository
                source.component = manifest.component
                source.version_ref = manifest.requested_ref
                source.snapshot_commit_sha = manifest.commit_sha

            if deleted_paths:
                await session.execute(
                    delete(SourceFileState).where(
                        SourceFileState.source_id == manifest.source_id,
                        SourceFileState.path.in_(deleted_paths),
                    )
                )

            for path, source_file in current_by_path.items():
                row = await session.get(
                    SourceFileState,
                    {"source_id": manifest.source_id, "path": path},
                )
                previous = previous_files.get(path)
                content_commit_sha = (
                    manifest.commit_sha
                    if path in changed_paths or previous is None
                    else previous.content_commit_sha
                )
                if row is None:
                    row = SourceFileState(
                        source_id=manifest.source_id,
                        path=path,
                        blob_sha=source_file.sha,
                        content_commit_sha=content_commit_sha,
                        last_seen_snapshot_commit_sha=manifest.commit_sha,
                        size_bytes=source_file.size,
                        content_type=source_file.content_type,
                    )
                    session.add(row)
                else:
                    row.blob_sha = source_file.sha
                    row.content_commit_sha = content_commit_sha
                    row.last_seen_snapshot_commit_sha = manifest.commit_sha
                    row.size_bytes = source_file.size
                    row.content_type = source_file.content_type

            run = await session.get(IngestionRun, run_id)
            if run is None:
                raise RuntimeError(f"Ingestion run {run_id} does not exist")
            run.status = "succeeded"
            run.added_count = len(added_paths)
            run.modified_count = len(modified_paths)
            run.deleted_count = len(deleted_paths)
            run.unchanged_count = len(unchanged_paths)
            run.fetched_count = fetched_count
            run.chunk_count = chunk_count
            run.indexed_count = indexed_count
            run.finished_at = datetime.now(UTC)
            source.last_successful_run_id = run_id

    async def fail_run(self, run_id: str, error: Exception | str) -> None:
        message = str(error)
        async with self.sessions.begin() as session:
            run = await session.get(IngestionRun, run_id)
            if run is None:
                return
            run.status = "failed"
            run.error_message = message[:10_000]
            run.finished_at = datetime.now(UTC)
