import json
from pathlib import Path

import pytest

from app.evaluation.performance_cli import (
    build_candidates,
    load_cases,
    percentile,
    summarize_ms,
)


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
