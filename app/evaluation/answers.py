import json
from dataclasses import dataclass
from pathlib import Path

from app.generation.models import GroundedAnswer


@dataclass(frozen=True)
class AnswerEvalCase:
    id: str
    category: str
    question: str
    answerable: bool
    expected_sources: tuple[str, ...]
    expected_terms: tuple[str, ...]


@dataclass(frozen=True)
class AnswerCaseResult:
    case_id: str
    answerable: bool
    correct: bool
    false_abstention: bool
    unsafe_answer: bool
    citations_correct: int
    citations_assessed: int
    claims_supported: int
    claims_total: int
    expected_terms_present: bool


@dataclass(frozen=True)
class AnswerEvaluationMetrics:
    cases: int
    answerable_cases: int
    unanswerable_cases: int
    grounded_answer_accuracy: float
    citation_correctness: float
    claim_support_rate: float
    false_abstention_rate: float
    unsafe_answer_rate: float


def load_answer_benchmark(path: Path) -> list[AnswerEvalCase]:
    cases: list[AnswerEvalCase] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        cases.append(
            AnswerEvalCase(
                id=str(raw["id"]),
                category=str(raw["category"]),
                question=str(raw["question"]),
                answerable=bool(raw["answerable"]),
                expected_sources=tuple(
                    str(item) for item in raw.get("expected_sources", [])
                ),
                expected_terms=tuple(
                    str(item) for item in raw.get("expected_terms", [])
                ),
            )
        )
    return cases


def evaluate_answer_case(
    case: AnswerEvalCase,
    answer: GroundedAnswer,
) -> AnswerCaseResult:
    normalized_answer = answer.answer.casefold()
    expected_terms_present = all(
        term.casefold() in normalized_answer for term in case.expected_terms
    )

    citations_correct = 0
    citations_assessed = 0
    if answer.citations:
        if case.answerable and case.expected_sources:
            citations_assessed = len(answer.citations)
            citations_correct = sum(
                citation.source_id in case.expected_sources
                for citation in answer.citations
            )
        elif not case.answerable:
            citations_assessed = len(answer.citations)

    claims_supported = 0
    claims_total = 0
    if answer.verification is not None:
        claims_total = len(answer.verification.claims)
        claims_supported = sum(
            claim.supported for claim in answer.verification.claims
        )

    source_ok = True
    if case.expected_sources:
        source_ok = bool(answer.citations) and all(
            citation.source_id in case.expected_sources
            for citation in answer.citations
        )

    verification_ok = (
        answer.verification is not None and answer.verification.passed
    )

    if case.answerable:
        correct = (
            answer.grounded
            and not answer.abstained
            and source_ok
            and expected_terms_present
            and verification_ok
        )
        false_abstention = answer.abstained
        unsafe_answer = False
    else:
        correct = answer.abstained and not answer.grounded
        false_abstention = False
        unsafe_answer = answer.grounded and not answer.abstained

    return AnswerCaseResult(
        case_id=case.id,
        answerable=case.answerable,
        correct=correct,
        false_abstention=false_abstention,
        unsafe_answer=unsafe_answer,
        citations_correct=citations_correct,
        citations_assessed=citations_assessed,
        claims_supported=claims_supported,
        claims_total=claims_total,
        expected_terms_present=expected_terms_present,
    )


def aggregate_answer_metrics(
    results: list[AnswerCaseResult],
) -> AnswerEvaluationMetrics:
    if not results:
        return AnswerEvaluationMetrics(
            cases=0,
            answerable_cases=0,
            unanswerable_cases=0,
            grounded_answer_accuracy=0.0,
            citation_correctness=0.0,
            claim_support_rate=0.0,
            false_abstention_rate=0.0,
            unsafe_answer_rate=0.0,
        )

    answerable = [result for result in results if result.answerable]
    unanswerable = [result for result in results if not result.answerable]

    citation_total = sum(result.citations_assessed for result in results)
    citation_correct = sum(result.citations_correct for result in results)
    claim_total = sum(result.claims_total for result in results)
    claim_supported = sum(result.claims_supported for result in results)

    return AnswerEvaluationMetrics(
        cases=len(results),
        answerable_cases=len(answerable),
        unanswerable_cases=len(unanswerable),
        grounded_answer_accuracy=(
            sum(result.correct for result in results) / len(results)
        ),
        citation_correctness=(
            citation_correct / citation_total if citation_total else 0.0
        ),
        claim_support_rate=(
            claim_supported / claim_total if claim_total else 0.0
        ),
        false_abstention_rate=(
            sum(result.false_abstention for result in answerable)
            / len(answerable)
            if answerable
            else 0.0
        ),
        unsafe_answer_rate=(
            sum(result.unsafe_answer for result in unanswerable)
            / len(unanswerable)
            if unanswerable
            else 0.0
        ),
    )
