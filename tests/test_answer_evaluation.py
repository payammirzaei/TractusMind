from app.evaluation.answers import (
    AnswerEvalCase,
    aggregate_answer_metrics,
    evaluate_answer_case,
)
from app.evaluation.calibration import (
    CalibrationSample,
    calibrate_threshold,
)
from app.generation.models import (
    AnswerCitation,
    ClaimVerdict,
    GroundedAnswer,
    VerificationReport,
)


def _case(*, answerable: bool = True) -> AnswerEvalCase:
    return AnswerEvalCase(
        id="case-1",
        category="coding",
        question="How do I create an asset?",
        answerable=answerable,
        expected_sources=("tractusx-sdk",) if answerable else (),
        expected_terms=("asset",) if answerable else (),
    )


def _citation() -> AnswerCitation:
    return AnswerCitation(
        citation_id="S1",
        chunk_id="chunk-1",
        source_id="tractusx-sdk",
        repository="eclipse-tractusx/tractusx-sdk",
        component="sdk",
        commit_sha="a" * 40,
        path="tractusx_sdk/connector.py",
        start_line=10,
        end_line=20,
        source_url="https://example.test/source#L10-L20",
        rerank_score=0.9,
    )


def _verification(*, passed: bool = True) -> VerificationReport:
    return VerificationReport(
        passed=passed,
        claims=[
            ClaimVerdict(
                claim="The SDK can create an asset.",
                citation_ids=["S1"],
                supported=passed,
            )
        ],
        unsupported_claim_count=0 if passed else 1,
    )


def test_answer_metrics_accept_grounded_supported_answer() -> None:
    answer = GroundedAnswer(
        question="How do I create an asset?",
        answer="Create an asset with the SDK [S1].",
        grounded=True,
        abstained=False,
        evidence_count=1,
        citations=[_citation()],
        verification=_verification(),
        model="test-model",
    )

    result = evaluate_answer_case(_case(), answer)
    metrics = aggregate_answer_metrics([result])

    assert result.correct is True
    assert metrics.grounded_answer_accuracy == 1.0
    assert metrics.citation_correctness == 1.0
    assert metrics.claim_support_rate == 1.0
    assert metrics.false_abstention_rate == 0.0


def test_answer_metrics_count_false_abstention() -> None:
    answer = GroundedAnswer(
        question="How do I create an asset?",
        answer="Insufficient evidence.",
        grounded=False,
        abstained=True,
        evidence_count=0,
    )

    result = evaluate_answer_case(_case(), answer)
    metrics = aggregate_answer_metrics([result])

    assert result.correct is False
    assert metrics.false_abstention_rate == 1.0


def test_answer_metrics_count_unsafe_answer() -> None:
    answer = GroundedAnswer(
        question="What is tomorrow's weather?",
        answer="It will be sunny [S1].",
        grounded=True,
        abstained=False,
        evidence_count=1,
        citations=[_citation()],
        verification=_verification(),
    )

    result = evaluate_answer_case(_case(answerable=False), answer)
    metrics = aggregate_answer_metrics([result])

    assert result.unsafe_answer is True
    assert metrics.unsafe_answer_rate == 1.0
    assert metrics.citation_correctness == 0.0


def test_calibration_prefers_zero_unsafe_acceptance() -> None:
    samples = [
        CalibrationSample("a1", True, 0.9),
        CalibrationSample("a2", True, 0.8),
        CalibrationSample("n1", False, 0.4),
        CalibrationSample("n2", False, 0.2),
    ]

    result = calibrate_threshold(samples, max_unsafe_rate=0.0)

    assert result.recommended_threshold > 0.4
    assert result.metrics.true_accept_rate == 1.0
    assert result.metrics.unsafe_evidence_accept_rate == 0.0
