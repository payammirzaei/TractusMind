import json
from pathlib import Path

import pytest

from app.evaluation.performance_cli import (
    build_candidates,
    load_cases,
    percentile,
    summarize_ms,
)
from app.evaluation.performance_gate import evaluate_performance_budget


def test_percentile_interpolates_and_validates() -> None:
    assert percentile([1.0], 0.95) == 1.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.5) == pytest.approx(2.5)
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.95) == pytest.approx(3.85)

    with pytest.raises(ValueError, match="empty"):
        percentile([], 0.5)
    with pytest.raises(ValueError, match="between zero and one"):
        percentile([1.0], 1.1)


def test_summarize_ms_reports_expected_shape() -> None:
    summary = summarize_ms([0.1, 0.2, 0.3])

    assert summary["samples"] == 3.0
    assert summary["min_ms"] == pytest.approx(100.0)
    assert summary["p50_ms"] == pytest.approx(200.0)
    assert summary["max_ms"] == pytest.approx(300.0)


def test_load_cases_and_build_candidates(tmp_path: Path) -> None:
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "id": "sdk-case",
                "category": "coding",
                "question": "How do I use the SDK?",
                "expected_sources": ["tractusx-sdk"],
                "expected_terms": ["asset"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    cases = load_cases(dataset)
    candidates = build_candidates(cases, count=3, target_chars=500)

    assert len(cases) == 1
    assert len(candidates) == 3
    assert all(len(candidate.text) == 500 for candidate in candidates)
    assert candidates[0].source_id == "tractusx-sdk"
    assert candidates[0].retrieval_methods == ["dense", "sparse"]


def _performance_report(*, combined_p95_ms: float = 1228.5) -> dict[str, object]:
    return {
        "environment": {
            "cpu_affinity": [0, 1],
            "max_rss_mb": 901.7,
        },
        "workload": {
            "candidates_per_query": 20,
            "candidate_chars": 1200,
            "rerank_limit": 6,
        },
        "steady_state": {
            "dense_query": {"p95_ms": 71.8},
            "sparse_query": {"p95_ms": 0.43},
            "rerank": {"p95_ms": 1172.5},
            "combined_model_compute": {"p95_ms": combined_p95_ms},
        },
    }


def _write_budget(path: Path) -> None:
    path.write_text(
        """
[workload]
cpu_count = 2
candidate_count = 20
candidate_chars = 1200
rerank_limit = 6

[budget]
dense_query_p95_ms = 150.0
sparse_query_p95_ms = 10.0
rerank_p95_ms = 1650.0
combined_model_compute_p95_ms = 1750.0
max_rss_mb = 1536.0
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_performance_budget_passes_measured_baseline(tmp_path: Path) -> None:
    budget = tmp_path / "performance_gate.toml"
    _write_budget(budget)

    gate, violations = evaluate_performance_budget(_performance_report(), budget)

    assert violations == []
    assert gate["status"] == "pass"
    assert gate["workload_checks"]["candidate_count"]["passed"] is True
    assert gate["budget_checks"]["combined_model_compute_p95_ms"]["passed"] is True


def test_performance_budget_fails_regression_after_recording_evidence(tmp_path: Path) -> None:
    budget = tmp_path / "performance_gate.toml"
    _write_budget(budget)

    gate, violations = evaluate_performance_budget(
        _performance_report(combined_p95_ms=1900.0),
        budget,
    )

    assert gate["status"] == "fail"
    assert any("combined_model_compute_p95_ms exceeded budget" in item for item in violations)
