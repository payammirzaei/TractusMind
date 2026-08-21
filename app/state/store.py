from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.db import verify_database_revision
from app.ingestion.models import SourceManifest
from app.state.models import IngestionRun, SourceFileState, SourceState


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


@dataclass(frozen=True)
class SourceStatusRecord:
    source_id: str
    repository: str
    component: str
    version_ref: str
    snapshot_commit_sha: str
    last_successful_run_id: str | None
    updated_at: datetime
    file_count: int


@dataclass(frozen=True)
class IngestionRunRecord:
    run_id: str
    source_id: str
    repository: str
    requested_ref: str
    snapshot_commit_sha: str
    status: str
    discovered_count: int
    added_count: int
    modified_count: int
    deleted_count: int
    unchanged_count: int
    fetched_count: int
    chunk_count: int
    indexed_count: int
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None


class SourceStateStore:
    """Persist successful source snapshots and ingestion-run audit data."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self.sessions = async_sessionmaker(engine, expire_on_commit=False)
        self._schema_ready = False

    async def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        await verify_database_revision(self.engine)
        self._schema_ready = True

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

    async def list_source_statuses(self) -> list[SourceStatusRecord]:
        async with self.sessions() as session:
            sources = (
                await session.scalars(select(SourceState).order_by(SourceState.source_id))
            ).all()
            count_rows = (
                await session.execute(
                    select(
                        SourceFileState.source_id,
                        func.count(SourceFileState.path),
                    ).group_by(SourceFileState.source_id)
                )
            ).all()
        file_counts = {source_id: int(count) for source_id, count in count_rows}
        return [
            SourceStatusRecord(
                source_id=row.source_id,
                repository=row.repository,
                component=row.component,
                version_ref=row.version_ref,
                snapshot_commit_sha=row.snapshot_commit_sha,
                last_successful_run_id=row.last_successful_run_id,
                updated_at=row.updated_at,
                file_count=file_counts.get(row.source_id, 0),
            )
            for row in sources
        ]

    async def get_source_status(self, source_id: str) -> SourceStatusRecord | None:
        statuses = await self.list_source_statuses()
        return next((item for item in statuses if item.source_id == source_id), None)

    async def list_runs(
        self,
        *,
        source_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[IngestionRunRecord]:
        query = select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(limit)
        if source_id is not None:
            query = query.where(IngestionRun.source_id == source_id)
        if status is not None:
            query = query.where(IngestionRun.status == status)

        async with self.sessions() as session:
            rows = (await session.scalars(query)).all()
        return [self._run_record(row) for row in rows]

    async def get_run(self, run_id: str) -> IngestionRunRecord | None:
        async with self.sessions() as session:
            row = await session.get(IngestionRun, run_id)
        return self._run_record(row) if row is not None else None

    async def run_status_counts(self) -> dict[str, int]:
        async with self.sessions() as session:
            rows = (
                await session.execute(
                    select(IngestionRun.status, func.count(IngestionRun.run_id)).group_by(
                        IngestionRun.status
                    )
                )
            ).all()
        return {status: int(count) for status, count in rows}

    async def start_run(self, manifest: SourceManifest) -> str:
        run = IngestionRun(
            source_id=manifest.source_id,
            repository=manifest.repository,
            requested_ref=manifest.requested_ref,
            snapshot_commit_sha=manifest.commit_sha,
            discovered_count=len(manifest.files),
        )
        now = datetime.now(UTC)
        async with self.sessions.begin() as session:
            stale_runs = (
                await session.scalars(
                    select(IngestionRun).where(
                        IngestionRun.source_id == manifest.source_id,
                        IngestionRun.status == "running",
                    )
                )
            ).all()
            for stale in stale_runs:
                stale.status = "failed"
                stale.error_message = (
                    "Interrupted before completion; superseded by a newer source sync run"
                )
                stale.finished_at = now
            session.add(run)
        return run.run_id

    async def update_run_progress(
        self,
        run_id: str,
        *,
        added_count: int | None = None,
        modified_count: int | None = None,
        deleted_count: int | None = None,
        unchanged_count: int | None = None,
        fetched_count: int | None = None,
        chunk_count: int | None = None,
        indexed_count: int | None = None,
    ) -> None:
        updates = {
            "added_count": added_count,
            "modified_count": modified_count,
            "deleted_count": deleted_count,
            "unchanged_count": unchanged_count,
            "fetched_count": fetched_count,
            "chunk_count": chunk_count,
            "indexed_count": indexed_count,
        }
        async with self.sessions.begin() as session:
            run = await session.get(IngestionRun, run_id)
            if run is None or run.status != "running":
                return
            for field, value in updates.items():
                if value is not None:
                    setattr(run, field, value)

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

    def _run_record(self, row: IngestionRun) -> IngestionRunRecord:
        return IngestionRunRecord(
            run_id=row.run_id,
            source_id=row.source_id,
            repository=row.repository,
            requested_ref=row.requested_ref,
            snapshot_commit_sha=row.snapshot_commit_sha,
            status=row.status,
            discovered_count=row.discovered_count,
            added_count=row.added_count,
            modified_count=row.modified_count,
            deleted_count=row.deleted_count,
            unchanged_count=row.unchanged_count,
            fetched_count=row.fetched_count,
            chunk_count=row.chunk_count,
            indexed_count=row.indexed_count,
            error_message=row.error_message,
            started_at=row.started_at,
            finished_at=row.finished_at,
        )
