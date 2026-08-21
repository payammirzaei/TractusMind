import argparse
import asyncio
import json
import os
import platform
import resource
import statistics
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from app.core.config import Settings
from app.embeddings.service import DenseEmbeddingService
from app.embeddings.sparse import SparseEmbeddingService
from app.reranking.service import CrossEncoderReranker
from app.retrieval.models import RetrievalHit


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    category: str
    question: str
    expected_sources: tuple[str, ...]
    expected_terms: tuple[str, ...]


def load_cases(path: Path) -> list[BenchmarkCase]:
    cases: list[BenchmarkCase] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        cases.append(
            BenchmarkCase(
                case_id=str(payload["id"]),
                category=str(payload.get("category", "unknown")),
                question=str(payload["question"]),
                expected_sources=tuple(str(item) for item in payload.get("expected_sources", [])),
                expected_terms=tuple(str(item) for item in payload.get("expected_terms", [])),
            )
        )
    if not cases:
        raise ValueError(f"No benchmark cases found in {path}")
    return cases


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        raise ValueError("Cannot calculate a percentile from an empty sample")
    if not 0.0 <= quantile <= 1.0:
        raise ValueError("quantile must be between zero and one")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def summarize_ms(values: list[float]) -> dict[str, float]:
    milliseconds = [value * 1000.0 for value in values]
    return {
        "samples": float(len(milliseconds)),
        "min_ms": min(milliseconds),
        "mean_ms": statistics.fmean(milliseconds),
        "p50_ms": percentile(milliseconds, 0.50),
        "p95_ms": percentile(milliseconds, 0.95),
        "max_ms": max(milliseconds),
    }


def _candidate_text(case: BenchmarkCase, index: int, target_chars: int) -> str:
    source = case.expected_sources[0] if case.expected_sources else "tractusx-docs"
    terms = ", ".join(case.expected_terms) or "grounded source evidence"
    paragraph = (
        f"Representative Tractus-X retrieval candidate {index + 1}. "
        f"Source family: {source}. Category: {case.category}. "
        f"Engineering topic: {case.question} Relevant terms: {terms}. "
        "This benchmark payload approximates the amount of text passed from hybrid retrieval "
        "into the production cross-encoder. It is deterministic and is used only to measure "
        "CPU inference cost; it is not product evidence and is never shown to users. "
    )
    repetitions = max(1, (target_chars + len(paragraph) - 1) // len(paragraph))
    return (paragraph * repetitions)[:target_chars]


def build_candidates(
    cases: list[BenchmarkCase],
    *,
    count: int,
    target_chars: int,
) -> list[RetrievalHit]:
    candidates: list[RetrievalHit] = []
    for index in range(count):
        case = cases[index % len(cases)]
        source = case.expected_sources[0] if case.expected_sources else "tractusx-docs"
        candidates.append(
            RetrievalHit(
                chunk_id=f"perf-{index:03d}",
                score=1.0 / (index + 1),
                retrieval_methods=["dense", "sparse"],
                text=_candidate_text(case, index, target_chars),
                source_id=source,
                repository=f"eclipse-tractusx/{source}",
                component=source,
                version_ref="main",
                snapshot_commit_sha="a" * 40,
                commit_sha="a" * 40,
                path=f"benchmark/{case.case_id}.md",
                content_type="documentation",
                language="markdown",
                kind="section",
                start_line=1,
                end_line=20,
                section_path=[case.category],
                source_url=f"https://github.com/eclipse-tractusx/{source}",
            )
        )
    return candidates


def _rss_mb() -> float:
    # Linux reports ru_maxrss in KiB. The performance workflow is intentionally Linux-only.
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


async def measure(args: argparse.Namespace) -> dict[str, object]:
    settings = Settings()
    cases = load_cases(args.dataset)
    candidates = build_candidates(
        cases,
        count=args.candidate_count,
        target_chars=args.candidate_chars,
    )

    dense = DenseEmbeddingService(
        settings.embedding_model,
        batch_size=settings.embedding_batch_size,
    )
    sparse = SparseEmbeddingService(
        settings.sparse_embedding_model,
        batch_size=settings.sparse_embedding_batch_size,
    )
    reranker = CrossEncoderReranker(
        settings.reranker_model,
        batch_size=settings.reranker_batch_size,
    )

    cold: dict[str, float] = {}
    first_query = cases[0].question

    started = perf_counter()
    await dense.embed_query(first_query)
    cold["dense_query_seconds"] = perf_counter() - started

    started = perf_counter()
    await sparse.embed_query(first_query)
    cold["sparse_query_seconds"] = perf_counter() - started

    started = perf_counter()
    await reranker.rerank(first_query, candidates, limit=args.rerank_limit)
    cold["rerank_seconds"] = perf_counter() - started
    cold["combined_model_seconds"] = sum(cold.values())

    dense_samples: list[float] = []
    sparse_samples: list[float] = []
    rerank_samples: list[float] = []
    combined_samples: list[float] = []

    for _ in range(args.iterations):
        for case in cases:
            combined_started = perf_counter()

            stage_started = perf_counter()
            await dense.embed_query(case.question)
            dense_samples.append(perf_counter() - stage_started)

            stage_started = perf_counter()
            await sparse.embed_query(case.question)
            sparse_samples.append(perf_counter() - stage_started)

            stage_started = perf_counter()
            await reranker.rerank(case.question, candidates, limit=args.rerank_limit)
            rerank_samples.append(perf_counter() - stage_started)

            combined_samples.append(perf_counter() - combined_started)

    return {
        "schema_version": 1,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
            "cpu_affinity": sorted(os.sched_getaffinity(0)),
            "max_rss_mb": _rss_mb(),
        },
        "models": {
            "dense": settings.embedding_model,
            "sparse": settings.sparse_embedding_model,
            "reranker": settings.reranker_model,
        },
        "workload": {
            "queries": len(cases),
            "iterations": args.iterations,
            "samples": len(combined_samples),
            "candidates_per_query": args.candidate_count,
            "candidate_chars": args.candidate_chars,
            "rerank_limit": args.rerank_limit,
        },
        "cold_start": cold,
        "steady_state": {
            "dense_query": summarize_ms(dense_samples),
            "sparse_query": summarize_ms(sparse_samples),
            "rerank": summarize_ms(rerank_samples),
            "combined_model_compute": summarize_ms(combined_samples),
        },
        "notes": [
            "Combined model compute measures dense query embedding, sparse query embedding, "
            "and reranking sequentially, matching the current CPU model order.",
            "Qdrant network/search latency and external LLM latency are intentionally excluded.",
            "Cold-start timings include local model initialization and may include first-run downloads.",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure CPU-only retrieval model latency using the production model stack."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("benchmarks/full_corpus_v1.jsonl"),
    )
    parser.add_argument("--iterations", type=int, default=2)
    parser.add_argument("--candidate-count", type=int, default=20)
    parser.add_argument("--candidate-chars", type=int, default=1200)
    parser.add_argument("--rerank-limit", type=int, default=6)
    parser.add_argument("--output", type=Path, default=Path("artifacts/cpu-performance.json"))
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be greater than zero")
    if args.candidate_count < 1:
        parser.error("--candidate-count must be greater than zero")
    if args.candidate_chars < 100:
        parser.error("--candidate-chars must be at least 100")
    if args.rerank_limit < 1 or args.rerank_limit > args.candidate_count:
        parser.error("--rerank-limit must be between 1 and --candidate-count")

    report = asyncio.run(measure(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
