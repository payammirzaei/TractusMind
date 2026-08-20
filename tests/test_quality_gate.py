from app.evaluation.quality_gate import GateConfig, evaluate_gate


def _config(*, threshold: float | None = None) -> GateConfig:
    return GateConfig(
        max_unsafe_answer_rate=0.0,
        max_unsafe_evidence_accept_rate=0.0,
        require_all_reviewed_regressions=True,
        minimum_relevance_score=threshold,
        threshold_tolerance=1e-6,
    )


def test_quality_gate_passes_safe_calibration_and_reviewed_regressions() -> None:
    violations = evaluate_gate(
        config=_config(threshold=0.42),
        calibration_report={
            "recommended_threshold": 0.42,
            "metrics": {"unsafe_evidence_accept_rate": 0.0},
        },
        answer_report={"metrics": {"unsafe_answer_rate": 0.0}},
        retrieval_regression_report={
            "reports": [
                {
                    "details": [
                        {"id": "retrieval-1", "hit": True},
                        {"id": "retrieval-2", "hit": True},
                    ]
                }
            ]
        },
        debug_regression_report={
            "reports": [{"details": [{"id": "debug-1", "hit": True}]}]
        },
        answer_regression_report={
            "metrics": {"unsafe_answer_rate": 0.0},
            "details": [{"id": "answer-1", "correct": True}],
        },
        require_pinned_threshold=True,
    )

    assert violations == []


def test_quality_gate_fails_any_reviewed_regression() -> None:
    violations = evaluate_gate(
        config=_config(),
        retrieval_regression_report={
            "reports": [{"details": [{"id": "retrieval-1", "hit": False}]}]
        },
    )

    assert len(violations) == 1
    assert violations[0].check == "retrieval-regressions"
    assert "retrieval-1" in violations[0].detail


def test_quality_gate_fails_unsafe_answer_rate() -> None:
    violations = evaluate_gate(
        config=_config(),
        answer_report={"metrics": {"unsafe_answer_rate": 0.25}},
    )

    assert len(violations) == 1
    assert violations[0].check == "answer-unsafe-answer-rate"


def test_quality_gate_requires_measured_threshold_when_requested() -> None:
    violations = evaluate_gate(
        config=_config(),
        calibration_report={
            "recommended_threshold": 0.42,
            "metrics": {"unsafe_evidence_accept_rate": 0.0},
        },
        require_pinned_threshold=True,
    )

    assert len(violations) == 1
    assert violations[0].check == "pinned-threshold"


def test_quality_gate_detects_threshold_drift() -> None:
    violations = evaluate_gate(
        config=_config(threshold=0.42),
        calibration_report={
            "recommended_threshold": 0.47,
            "metrics": {"unsafe_evidence_accept_rate": 0.0},
        },
        require_pinned_threshold=True,
    )

    assert len(violations) == 1
    assert violations[0].check == "threshold-drift"
