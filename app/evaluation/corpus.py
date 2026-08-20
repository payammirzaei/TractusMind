import hashlib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from qdrant_client import AsyncQdrantClient, models

from app.core.config import Settings
from app.infra.postgres import create_postgres_engine
from app.infra.qdrant import create_qdrant_client
from app.ingestion.github_client import GitHubApiClient, GitHubSourceError
from app.ingestion.models import SourceDefinition
from app.ingestion.registry import DEFAULT_REGISTRY_PATH, get_enabled_sources
from app.retrieval.qdrant_store import model_scoped_collection_name
from app.state import SourceStateStore
from app.state.store import IngestionRunRecord, SourceStatusRecord


@dataclass(frozen=True)
class IndexedSourceCounts:
    current_snapshot_chunks: int
    total_source_chunks: int

    @property
    def stale_snapshot_chunks(self) -> int:
        return max(0, self.total_source_chunks - self.current_snapshot_chunks)


@dataclass(frozen=True)
class CorpusViolation:
    check: str
    source_id: str | None
    detail: str


@dataclass(frozen=True)
class CorpusSourceReport:
    source_id: str
    repository: str
    component: str
    version_ref: str
    snapshot_commit_sha: str | None
    upstream_commit_sha: str | None
    last_successful_run_id: str | None
    file_count: int
    current_snapshot_chunks: int
    total_source_chunks: int
    stale_snapshot_chunks: int
    passed: bool


@dataclass(frozen=True)
class CorpusValidationReport:
    generated_at: str
    registry_path: str
    registry_sha256: str
    collection_name: str
    embedding_model: str
    sparse_model: str
    reranker_model: str
    enabled_source_count: int
    upstream_verified: bool
    passed: bool
    sources: tuple[CorpusSourceReport, ...]
    violations: tuple[CorpusViolation, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            **asdict(self),
            "sources": [asdict(source) for source in self.sources],
            "violations": [asdict(violation) for violation in self.violations],
        }


def evaluate_corpus_contract(
    *,
    sources: list[SourceDefinition],
    statuses: list[SourceStatusRecord],
    runs: dict[str, IngestionRunRecord],
    counts: dict[str, IndexedSourceCounts],
    collection_exists: bool,
    settings: Settings,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    upstream_commits: dict[str, str | None] | None = None,
) -> CorpusValidationReport:
    violations: list[CorpusViolation] = []
    reports: list[CorpusSourceReport] = []
    statuses_by_id = {status.source_id: status for status in statuses}

    if not collection_exists:
        violations.append(
            CorpusViolation(
                check="collection-exists",
                source_id=None,
                detail="model-scoped Qdrant collection does not exist",
            )
        )

    for source in sources:
        source_violations_before = len(violations)
        status = statuses_by_id.get(source.id)
        source_counts = counts.get(source.id, IndexedSourceCounts(0, 0))
        upstream_commit = (
            upstream_commits.get(source.id) if upstream_commits is not None else None
        )

        if upstream_commits is not None and not upstream_commit:
            violations.append(
                CorpusViolation(
                    check="upstream-ref",
                    source_id=source.id,
                    detail=f"could not resolve current upstream ref {source.ref}",
                )
            )

        if status is None:
            violations.append(
                CorpusViolation(
                    check="source-state",
                    source_id=source.id,
                    detail="enabled source has no successful PostgreSQL source_state",
                )
            )
            reports.append(
                CorpusSourceReport(
                    source_id=source.id,
                    repository=source.full_name,
                    component=source.component,
                    version_ref=source.ref,
                    snapshot_commit_sha=None,
                    upstream_commit_sha=upstream_commit,
                    last_successful_run_id=None,
                    file_count=0,
                    current_snapshot_chunks=source_counts.current_snapshot_chunks,
                    total_source_chunks=source_counts.total_source_chunks,
                    stale_snapshot_chunks=source_counts.stale_snapshot_chunks,
                    passed=False,
                )
            )
            continue

        if status.repository != source.full_name:
            violations.append(
                CorpusViolation(
                    check="repository-match",
                    source_id=source.id,
                    detail=f"state has {status.repository}, registry expects {source.full_name}",
                )
            )
        if status.component != source.component:
            violations.append(
                CorpusViolation(
                    check="component-match",
                    source_id=source.id,
                    detail=f"state has {status.component}, registry expects {source.component}",
                )
            )
        if status.version_ref != source.ref:
            violations.append(
                CorpusViolation(
                    check="ref-match",
                    source_id=source.id,
                    detail=f"state has {status.version_ref}, registry expects {source.ref}",
                )
            )
        if upstream_commit and status.snapshot_commit_sha != upstream_commit:
            violations.append(
                CorpusViolation(
                    check="upstream-snapshot-match",
                    source_id=source.id,
                    detail=(
                        f"indexed snapshot {status.snapshot_commit_sha} is behind upstream "
                        f"{upstream_commit} for ref {source.ref}"
                    ),
                )
            )
        if status.file_count <= 0:
            violations.append(
                CorpusViolation(
                    check="source-files",
                    source_id=source.id,
                    detail="successful source state contains zero files",
                )
            )
        if not status.last_successful_run_id:
            violations.append(
                CorpusViolation(
                    check="successful-run",
                    source_id=source.id,
                    detail="source state has no last_successful_run_id",
                )
            )
        else:
            run = runs.get(status.last_successful_run_id)
            if run is None:
                violations.append(
                    CorpusViolation(
                        check="successful-run",
                        source_id=source.id,
                        detail="last_successful_run_id does not resolve to an ingestion run",
                    )
                )
            else:
                if run.status != "succeeded":
                    violations.append(
                        CorpusViolation(
                            check="successful-run",
                            source_id=source.id,
                            detail=f"last successful run is marked {run.status}",
                        )
                    )
                if run.snapshot_commit_sha != status.snapshot_commit_sha:
                    violations.append(
                        CorpusViolation(
                            check="snapshot-run-match",
                            source_id=source.id,
                            detail="source_state and last successful run use different snapshots",
                        )
                    )

        if source_counts.current_snapshot_chunks <= 0:
            violations.append(
                CorpusViolation(
                    check="indexed-current-snapshot",
                    source_id=source.id,
                    detail="Qdrant has no chunks for the successful source snapshot",
                )
            )
        if source_counts.stale_snapshot_chunks > 0:
            violations.append(
                CorpusViolation(
                    check="stale-snapshot-chunks",
                    source_id=source.id,
                    detail=(
                        f"Qdrant contains {source_counts.stale_snapshot_chunks} chunks "
                        "outside the successful source snapshot"
                    ),
                )
            )

        reports.append(
            CorpusSourceReport(
                source_id=source.id,
                repository=source.full_name,
                component=source.component,
                version_ref=source.ref,
                snapshot_commit_sha=status.snapshot_commit_sha,
                upstream_commit_sha=upstream_commit,
                last_successful_run_id=status.last_successful_run_id,
                file_count=status.file_count,
                current_snapshot_chunks=source_counts.current_snapshot_chunks,
                total_source_chunks=source_counts.total_source_chunks,
                stale_snapshot_chunks=source_counts.stale_snapshot_chunks,
                passed=len(violations) == source_violations_before,
            )
        )

    registry_bytes = registry_path.read_bytes()
    collection_name = model_scoped_collection_name(
        settings.qdrant_collection,
        settings.embedding_model,
        settings.sparse_embedding_model,
    )
    return CorpusValidationReport(
        generated_at=datetime.now(UTC).isoformat(),
        registry_path=str(registry_path),
        registry_sha256=hashlib.sha256(registry_bytes).hexdigest(),
        collection_name=collection_name,
        embedding_model=settings.embedding_model,
        sparse_model=settings.sparse_embedding_model,
        reranker_model=settings.reranker_model,
        enabled_source_count=len(sources),
        upstream_verified=upstream_commits is not None,
        passed=not violations,
        sources=tuple(reports),
        violations=tuple(violations),
    )


async def inspect_full_corpus(
    settings: Settings,
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    verify_upstream: bool = False,
) -> CorpusValidationReport:
    sources = get_enabled_sources(registry_path)
    engine = create_postgres_engine(settings)
    qdrant: AsyncQdrantClient = create_qdrant_client(settings)
    state = SourceStateStore(engine)
    github: GitHubApiClient | None = None
    try:
        await state.ensure_schema()
        statuses = await state.list_source_statuses()
        runs: dict[str, IngestionRunRecord] = {}
        for status in statuses:
            if status.last_successful_run_id:
                run = await state.get_run(status.last_successful_run_id)
                if run is not None:
                    runs[run.run_id] = run

        collection_name = model_scoped_collection_name(
            settings.qdrant_collection,
            settings.embedding_model,
            settings.sparse_embedding_model,
        )
        collection_exists = await qdrant.collection_exists(collection_name)
        counts: dict[str, IndexedSourceCounts] = {}
        if collection_exists:
            statuses_by_id = {status.source_id: status for status in statuses}
            for source in sources:
                status = statuses_by_id.get(source.id)
                total = await _count_chunks(qdrant, collection_name, source_id=source.id)
                current = 0
                if status is not None:
                    current = await _count_chunks(
                        qdrant,
                        collection_name,
                        source_id=source.id,
                        snapshot_commit_sha=status.snapshot_commit_sha,
                    )
                counts[source.id] = IndexedSourceCounts(
                    current_snapshot_chunks=current,
                    total_source_chunks=total,
                )

        upstream_commits: dict[str, str | None] | None = None
        if verify_upstream:
            upstream_commits = {}
            github = GitHubApiClient(
                token=settings.github_token,
                timeout=settings.github_timeout_seconds,
                max_attempts=settings.github_max_attempts,
                retry_base_seconds=settings.provider_retry_base_seconds,
                retry_max_seconds=settings.provider_retry_max_seconds,
                circuit_failure_threshold=settings.provider_circuit_failure_threshold,
                circuit_cooldown_seconds=settings.provider_circuit_cooldown_seconds,
            )
            for source in sources:
                try:
                    payload = await github.get_json(
                        f"/repos/{source.full_name}/commits/{source.ref}"
                    )
                    upstream_commits[source.id] = str(payload["sha"])
                except (GitHubSourceError, KeyError, TypeError):
                    upstream_commits[source.id] = None

        return evaluate_corpus_contract(
            sources=sources,
            statuses=statuses,
            runs=runs,
            counts=counts,
            collection_exists=collection_exists,
            settings=settings,
            registry_path=registry_path,
            upstream_commits=upstream_commits,
        )
    finally:
        if github is not None:
            await github.close()
        await qdrant.close()
        await engine.dispose()


async def _count_chunks(
    qdrant: AsyncQdrantClient,
    collection_name: str,
    *,
    source_id: str,
    snapshot_commit_sha: str | None = None,
) -> int:
    must = [
        models.FieldCondition(
            key="source_id",
            match=models.MatchValue(value=source_id),
        )
    ]
    if snapshot_commit_sha is not None:
        must.append(
            models.FieldCondition(
                key="snapshot_commit_sha",
                match=models.MatchValue(value=snapshot_commit_sha),
            )
        )
    result = await qdrant.count(
        collection_name=collection_name,
        count_filter=models.Filter(must=must),
        exact=True,
    )
    return int(result.count)
