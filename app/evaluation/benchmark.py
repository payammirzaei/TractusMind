import json
import math
from dataclasses import dataclass
from pathlib import Path

from app.retrieval.models import RetrievalHit


@dataclass(frozen=True)
class BenchmarkCase:
    id: str
    category: str
    question: str
    expected_sources: tuple[str, ...]
    expected_terms: tuple[str, ...]


@dataclass(frozen=True)
class BenchmarkMetrics:
    cases: int
    recall_at_k: float
    mrr: float
    ndcg_at_k: float


def load_benchmark(path: Path) -> list[BenchmarkCase]:
    cases: list[BenchmarkCase] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        cases.append(
            BenchmarkCase(
                id=str(raw["id"]),
                category=str(raw["category"]),
                question=str(raw["question"]),
                expected_sources=tuple(str(item) for item in raw.get("expected_sources", [])),
                expected_terms=tuple(str(item) for item in raw.get("expected_terms", [])),
            )
        )
    return cases


def is_relevant(case: BenchmarkCase, hit: RetrievalHit) -> bool:
    if case.expected_sources and hit.source_id not in case.expected_sources:
        return False
    if not case.expected_terms:
        return True

    searchable = " ".join(
        [
            hit.text,
            hit.path,
            hit.symbol or "",
            hit.parent_symbol or "",
            " ".join(hit.section_path),
        ]
    ).casefold()
    return all(term.casefold() in searchable for term in case.expected_terms)


def evaluate_case(case: BenchmarkCase, hits: list[RetrievalHit], k: int) -> tuple[int, float, float]:
    ranked = hits[:k]
    relevant_ranks = [rank for rank, hit in enumerate(ranked, start=1) if is_relevant(case, hit)]
    if not relevant_ranks:
        return 0, 0.0, 0.0

    first_rank = relevant_ranks[0]
    recall = 1
    reciprocal_rank = 1.0 / first_rank
    dcg = sum(1.0 / math.log2(rank + 1) for rank in relevant_ranks)
    ideal_count = len(relevant_ranks)
    ideal_dcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
    ndcg = dcg / ideal_dcg if ideal_dcg else 0.0
    return recall, reciprocal_rank, ndcg


def aggregate_metrics(results: list[tuple[int, float, float]]) -> BenchmarkMetrics:
    if not results:
        return BenchmarkMetrics(cases=0, recall_at_k=0.0, mrr=0.0, ndcg_at_k=0.0)
    count = len(results)
    return BenchmarkMetrics(
        cases=count,
        recall_at_k=sum(item[0] for item in results) / count,
        mrr=sum(item[1] for item in results) / count,
        ndcg_at_k=sum(item[2] for item in results) / count,
    )
