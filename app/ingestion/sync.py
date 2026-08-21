from dataclasses import dataclass

import structlog

from app.chunking import SmartChunker
from app.ingestion.incremental import IncrementalPlan, build_incremental_plan
from app.ingestion.models import SourceDefinition
from app.ingestion.pipeline import SourceIngestionPipeline
from app.retrieval.hybrid import HybridRetrievalService
from app.state.store import SourceStateStore

logger = structlog.get_logger()


@dataclass(frozen=True)
class IncrementalSyncResult:
    run_id: str
    source_id: str
    version_ref: str
    snapshot_commit_sha: str
    discovered_count: int
    added_count: int
    modified_count: int
    deleted_count: int
    unchanged_count: int
    fetched_count: int
    chunk_count: int
    indexed_count: int


class IncrementalSourceSync:
    """Apply one source snapshot while embedding only added or modified files."""

    def __init__(
        self,
        *,
        pipeline: SourceIngestionPipeline,
        retrieval: HybridRetrievalService,
        state: SourceStateStore,
        chunker: SmartChunker | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.retrieval = retrieval
        self.state = state
        self.chunker = chunker or SmartChunker()

    async def sync(self, source: SourceDefinition) -> IncrementalSyncResult:
        await self.state.ensure_schema()
        manifest = await self.pipeline.discover(source)
        previous_snapshot = await self.state.load_source_snapshot(manifest.source_id)
        previous_files = await self.state.load_file_states(manifest.source_id)
        plan = build_incremental_plan(manifest, previous_files)
        run_id = await self.state.start_run(manifest)

        await self.state.update_run_progress(
            run_id,
            added_count=len(plan.added),
            modified_count=len(plan.modified),
            deleted_count=len(plan.deleted_paths),
            unchanged_count=len(plan.unchanged),
        )
        logger.info(
            "ingestion_plan_ready",
            run_id=run_id,
            source_id=manifest.source_id,
            discovered_count=len(manifest.files),
            added_count=len(plan.added),
            modified_count=len(plan.modified),
            deleted_count=len(plan.deleted_paths),
            unchanged_count=len(plan.unchanged),
        )

        try:
            logger.info(
                "ingestion_fetch_started",
                run_id=run_id,
                source_id=manifest.source_id,
                file_count=len(plan.changed_files),
            )
            documents = await self.pipeline.fetch_files(manifest, plan.changed_files)
            await self.state.update_run_progress(run_id, fetched_count=len(documents))
            logger.info(
                "ingestion_fetch_succeeded",
                run_id=run_id,
                source_id=manifest.source_id,
                document_count=len(documents),
            )

            chunks = self.chunker.chunk_many(documents)
            await self.state.update_run_progress(run_id, chunk_count=len(chunks))
            logger.info(
                "ingestion_chunking_succeeded",
                run_id=run_id,
                source_id=manifest.source_id,
                chunk_count=len(chunks),
            )

            logger.info(
                "ingestion_index_started",
                run_id=run_id,
                source_id=manifest.source_id,
                chunk_count=len(chunks),
            )

            async def persist_index_progress(indexed_count: int) -> None:
                await self.state.update_run_progress(
                    run_id,
                    indexed_count=indexed_count,
                )

            indexed = (
                await self.retrieval.index(
                    chunks,
                    progress_callback=persist_index_progress,
                )
                if chunks
                else 0
            )
            logger.info(
                "ingestion_index_succeeded",
                run_id=run_id,
                source_id=manifest.source_id,
                indexed_count=indexed,
            )

            await self._apply_qdrant_snapshot(
                manifest_source_id=manifest.source_id,
                version_ref=manifest.requested_ref,
                snapshot_commit_sha=manifest.commit_sha,
                previous_snapshot_commit_sha=(
                    previous_snapshot.snapshot_commit_sha
                    if previous_snapshot is not None
                    else None
                ),
                plan=plan,
            )

            await self.state.complete_run(
                run_id=run_id,
                manifest=manifest,
                added_paths={item.path for item in plan.added},
                modified_paths={item.path for item in plan.modified},
                deleted_paths=set(plan.deleted_paths),
                unchanged_paths={item.path for item in plan.unchanged},
                fetched_count=len(documents),
                chunk_count=len(chunks),
                indexed_count=indexed,
                previous_files=previous_files,
            )
            logger.info(
                "ingestion_run_completed",
                run_id=run_id,
                source_id=manifest.source_id,
                indexed_count=indexed,
            )
        except Exception as exc:
            logger.exception(
                "ingestion_run_failed",
                run_id=run_id,
                source_id=manifest.source_id,
                error_type=type(exc).__name__,
            )
            await self.state.fail_run(run_id, exc)
            raise

        return IncrementalSyncResult(
            run_id=run_id,
            source_id=manifest.source_id,
            version_ref=manifest.requested_ref,
            snapshot_commit_sha=manifest.commit_sha,
            discovered_count=len(manifest.files),
            added_count=len(plan.added),
            modified_count=len(plan.modified),
            deleted_count=len(plan.deleted_paths),
            unchanged_count=len(plan.unchanged),
            fetched_count=len(documents),
            chunk_count=len(chunks),
            indexed_count=indexed,
        )

    async def _apply_qdrant_snapshot(
        self,
        *,
        manifest_source_id: str,
        version_ref: str,
        snapshot_commit_sha: str,
        previous_snapshot_commit_sha: str | None,
        plan: IncrementalPlan,
    ) -> None:
        snapshot_changed = previous_snapshot_commit_sha != snapshot_commit_sha
        unchanged_paths = [item.path for item in plan.unchanged]
        modified_paths = [item.path for item in plan.modified]

        if snapshot_changed and unchanged_paths:
            await self.retrieval.store.update_source_snapshot(
                source_id=manifest_source_id,
                paths=unchanged_paths,
                version_ref=version_ref,
                snapshot_commit_sha=snapshot_commit_sha,
            )

        if modified_paths:
            await self.retrieval.store.delete_source_paths(
                source_id=manifest_source_id,
                paths=modified_paths,
                keep_snapshot_commit_sha=snapshot_commit_sha,
            )

        if plan.deleted_paths:
            await self.retrieval.store.delete_source_paths(
                source_id=manifest_source_id,
                paths=plan.deleted_paths,
            )

        if previous_snapshot_commit_sha is None:
            await self.retrieval.store.remove_stale_source_versions(
                manifest_source_id,
                snapshot_commit_sha,
            )
