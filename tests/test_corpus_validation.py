from datetime import UTC, datetime
from pathlib import Path

from app.core.config import Settings
from app.evaluation.answers import load_answer_benchmark
from app.evaluation.benchmark import load_benchmark
from app.evaluation.corpus import IndexedSourceCounts, evaluate_corpus_contract
from app.ingestion.registry import get_enabled_sources
from app.state.store import IngestionRunRecord, SourceStatusRecord


def _status(source_id: str, repository: str, component: str, ref: str) -> SourceStatusRecord:
    return SourceStatusRecord(
        source_id=source_id,
        repository=repository,
        component=component,
        version_ref=ref,
        snapshot_commit_sha=f"{source_id}-snapshot",
        last_successful_run_id=f"{source_id}-run",
        updated_at=datetime.now(UTC),
        file_count=4,
    )


def _run(status: SourceStatusRecord) -> IngestionRunRecord:
    return IngestionRunRecord(
        run_id=status.last_successful_run_id or "missing",
        source_id=status.source_id,
        repository=status.repository,
        requested_ref=status.version_ref,
        snapshot_commit_sha=status.snapshot_commit_sha,
        status="succeeded",
        discovered_count=4,
        added_count=4,
        modified_count=0,
        deleted_count=0,
        unchanged_count=0,
        fetched_count=4,
        chunk_count=8,
        indexed_count=8,
        error_message=None,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )


def _healthy_contract_inputs():
    sources = get_enabled_sources()
    statuses = [
        _status(source.id, source.full_name, source.component, source.ref)
        for source in sources
    ]
    runs = {
        status.last_successful_run_id or "missing": _run(status)
        for status in statuses
    }
    counts = {
        source.id: IndexedSourceCounts(current_snapshot_chunks=8, total_source_chunks=8)
        for source in sources
    }
    return sources, statuses, runs, counts


def test_full_corpus_contract_passes_for_current_snapshots() -> None:
    sources, statuses, runs, counts = _healthy_contract_inputs()

    report = evaluate_corpus_contract(
        sources=sources,
        statuses=statuses,
        runs=runs,
        counts=counts,
        collection_exists=True,
        settings=Settings(),
    )

    assert report.passed is True
    assert report.enabled_source_count == len(sources)
    assert report.upstream_verified is False
    assert not report.violations
    assert all(source.passed for source in report.sources)


def test_full_corpus_contract_rejects_stale_or_missing_index_state() -> None:
    sources = get_enabled_sources()
    first = sources[0]
    status = _status(first.id, first.full_name, first.component, first.ref)

    report = evaluate_corpus_contract(
        sources=sources,
        statuses=[status],
        runs={status.last_successful_run_id or "missing": _run(status)},
        counts={
            first.id: IndexedSourceCounts(
                current_snapshot_chunks=5,
                total_source_chunks=7,
            )
        },
        collection_exists=True,
        settings=Settings(),
    )

    assert report.passed is False
    checks = {(item.check, item.source_id) for item in report.violations}
    assert ("stale-snapshot-chunks", first.id) in checks
    for source in sources[1:]:
        assert ("source-state", source.id) in checks


def test_full_corpus_contract_rejects_snapshot_behind_upstream() -> None:
    sources, statuses, runs, counts = _healthy_contract_inputs()
    upstream = {status.source_id: status.snapshot_commit_sha for status in statuses}
    upstream[sources[0].id] = "new-upstream-snapshot"

    report = evaluate_corpus_contract(
        sources=sources,
        statuses=statuses,
        runs=runs,
        counts=counts,
        collection_exists=True,
        settings=Settings(),
        upstream_commits=upstream,
    )

    assert report.passed is False
    assert report.upstream_verified is True
    assert any(
        violation.check == "upstream-snapshot-match"
        and violation.source_id == sources[0].id
        for violation in report.violations
    )


def test_v1_benchmarks_cover_every_enabled_source() -> None:
    enabled = {source.id for source in get_enabled_sources()}

    retrieval_cases = load_benchmark(Path("benchmarks/full_corpus_v1.jsonl"))
    retrieval_sources = {
        source_id
        for case in retrieval_cases
        for source_id in case.expected_sources
    }

    answer_cases = load_answer_benchmark(Path("benchmarks/answer_v1.jsonl"))
    answer_sources = {
        source_id
        for case in answer_cases
        if case.answerable
        for source_id in case.expected_sources
    }

    assert retrieval_sources == enabled
    assert answer_sources == enabled
    assert any(not case.answerable for case in answer_cases)
