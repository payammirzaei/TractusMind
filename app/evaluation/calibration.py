from dataclasses import dataclass


@dataclass(frozen=True)
class CalibrationSample:
    case_id: str
    answerable: bool
    top_rerank_score: float | None


@dataclass(frozen=True)
class ThresholdMetrics:
    threshold: float
    true_accept_rate: float
    false_abstention_rate: float
    unsafe_evidence_accept_rate: float
    balanced_accuracy: float


@dataclass(frozen=True)
class CalibrationResult:
    recommended_threshold: float
    max_unsafe_rate: float
    metrics: ThresholdMetrics
    candidates_tested: int


def evaluate_threshold(
    samples: list[CalibrationSample],
    threshold: float,
) -> ThresholdMetrics:
    answerable = [sample for sample in samples if sample.answerable]
    unanswerable = [sample for sample in samples if not sample.answerable]

    def accepted(sample: CalibrationSample) -> bool:
        score = sample.top_rerank_score
        return score is not None and score >= threshold

    true_accept_rate = (
        sum(accepted(sample) for sample in answerable) / len(answerable)
        if answerable
        else 0.0
    )
    false_abstention_rate = 1.0 - true_accept_rate if answerable else 0.0
    unsafe_accept_rate = (
        sum(accepted(sample) for sample in unanswerable) / len(unanswerable)
        if unanswerable
        else 0.0
    )
    true_reject_rate = 1.0 - unsafe_accept_rate if unanswerable else 1.0
    balanced_accuracy = (true_accept_rate + true_reject_rate) / 2.0

    return ThresholdMetrics(
        threshold=threshold,
        true_accept_rate=true_accept_rate,
        false_abstention_rate=false_abstention_rate,
        unsafe_evidence_accept_rate=unsafe_accept_rate,
        balanced_accuracy=balanced_accuracy,
    )


def calibrate_threshold(
    samples: list[CalibrationSample],
    *,
    max_unsafe_rate: float = 0.0,
) -> CalibrationResult:
    if not 0.0 <= max_unsafe_rate <= 1.0:
        raise ValueError("max_unsafe_rate must be between 0 and 1")

    scores = sorted(
        {
            sample.top_rerank_score
            for sample in samples
            if sample.top_rerank_score is not None
        }
    )
    if not scores:
        metrics = evaluate_threshold(samples, 0.0)
        return CalibrationResult(
            recommended_threshold=0.0,
            max_unsafe_rate=max_unsafe_rate,
            metrics=metrics,
            candidates_tested=1,
        )

    epsilon = 1e-6
    candidates = [scores[0] - epsilon, *scores, scores[-1] + epsilon]
    evaluations = [
        evaluate_threshold(samples, threshold) for threshold in candidates
    ]
    safe = [
        metrics
        for metrics in evaluations
        if metrics.unsafe_evidence_accept_rate <= max_unsafe_rate
    ]
    pool = safe or evaluations
    best = max(
        pool,
        key=lambda metrics: (
            metrics.true_accept_rate,
            metrics.balanced_accuracy,
            metrics.threshold,
        ),
    )

    return CalibrationResult(
        recommended_threshold=best.threshold,
        max_unsafe_rate=max_unsafe_rate,
        metrics=best,
        candidates_tested=len(candidates),
    )
