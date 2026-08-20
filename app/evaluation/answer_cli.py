import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from app.core.config import get_settings
from app.evaluation.answers import (
    aggregate_answer_metrics,
    evaluate_answer_case,
    load_answer_benchmark,
)
from app.evaluation.calibration import CalibrationSample, calibrate_threshold
from app.generation.factory import create_grounded_answer_service
from app.infra.qdrant import create_qdrant_client
from app.retrieval.factory import create_reranked_retrieval_service
from app.routing.service import QueryRouter


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tractusmind-answer-eval")
    subparsers = parser.add_subparsers(dest="command", required=True)

    evaluate = subparsers.add_parser(
        "evaluate",
        help="Run end-to-end grounded answer evaluation",
    )
    evaluate.add_argument(
        "--dataset",
        type=Path,
        default=Path("benchmarks/answer_v0.jsonl"),
    )
    evaluate.add_argument("--limit", type=int, default=None)

    calibrate = subparsers.add_parser(
        "calibrate",
        help="Calibrate the reranker evidence threshold",
    )
    calibrate.add_argument(
        "--dataset",
        type=Path,
        default=Path("benchmarks/answer_v0.jsonl"),
    )
    calibrate.add_argument("--limit", type=int, default=None)
    calibrate.add_argument(
        "--max-unsafe-rate",
        type=float,
        default=0.0,
    )
    return parser


async def _evaluate(args: argparse.Namespace) -> None:
    settings = get_settings()
    cases = load_answer_benchmark(args.dataset)
    if args.limit is not None:
        cases = cases[: args.limit]

    qdrant = create_qdrant_client(settings)
    service = create_grounded_answer_service(settings, qdrant)
    results = []
    details = []
    try:
        for case in cases:
            answer = await service.answer(case.question)
            result = evaluate_answer_case(case, answer)
            results.append(result)
            details.append(
                {
                    "id": case.id,
                    "answerable": case.answerable,
                    "correct": result.correct,
                    "grounded": answer.grounded,
                    "abstained": answer.abstained,
                    "route": (
                        answer.route.model_dump(mode="json")
                        if answer.route is not None
                        else None
                    ),
                    "citation_ids": [
                        citation.citation_id for citation in answer.citations
                    ],
                    "citation_sources": [
                        citation.source_id for citation in answer.citations
                    ],
                    "verification_passed": (
                        answer.verification.passed
                        if answer.verification is not None
                        else None
                    ),
                    "answer": answer.answer,
                }
            )
    finally:
        await service.close()
        await qdrant.close()

    metrics = aggregate_answer_metrics(results)
    print(
        json.dumps(
            {
                "dataset": str(args.dataset),
                "model": settings.llm_model,
                "minimum_relevance_score": settings.minimum_relevance_score,
                "metrics": {
                    key: round(value, 6) if isinstance(value, float) else value
                    for key, value in asdict(metrics).items()
                },
                "details": details,
            },
            indent=2,
        )
    )


async def _calibrate(args: argparse.Namespace) -> None:
    settings = get_settings()
    cases = load_answer_benchmark(args.dataset)
    if args.limit is not None:
        cases = cases[: args.limit]

    qdrant = create_qdrant_client(settings)
    retrieval = create_reranked_retrieval_service(settings, qdrant)
    router = QueryRouter()
    samples: list[CalibrationSample] = []
    route_details: dict[str, dict] = {}
    try:
        for case in cases:
            route = router.route(case.question)
            hits = await retrieval.search(
                case.question,
                limit=1,
                route=route,
            )
            score = None
            if hits:
                score = (
                    hits[0].rerank_score
                    if hits[0].rerank_score is not None
                    else hits[0].score
                )
            samples.append(
                CalibrationSample(
                    case_id=case.id,
                    answerable=case.answerable,
                    top_rerank_score=score,
                )
            )
            route_details[case.id] = route.model_dump(mode="json")
    finally:
        await qdrant.close()

    result = calibrate_threshold(
        samples,
        max_unsafe_rate=args.max_unsafe_rate,
    )
    print(
        json.dumps(
            {
                "dataset": str(args.dataset),
                "reranker_model": settings.reranker_model,
                "recommended_threshold": round(
                    result.recommended_threshold,
                    6,
                ),
                "recommended_env": (
                    "MINIMUM_RELEVANCE_SCORE="
                    f"{result.recommended_threshold:.6f}"
                ),
                "max_unsafe_rate": result.max_unsafe_rate,
                "candidates_tested": result.candidates_tested,
                "metrics": {
                    key: round(value, 6) if isinstance(value, float) else value
                    for key, value in asdict(result.metrics).items()
                },
                "samples": [
                    {
                        "id": sample.case_id,
                        "answerable": sample.answerable,
                        "route": route_details[sample.case_id],
                        "top_rerank_score": (
                            round(sample.top_rerank_score, 6)
                            if sample.top_rerank_score is not None
                            else None
                        ),
                    }
                    for sample in samples
                ],
            },
            indent=2,
        )
    )


async def _run(args: argparse.Namespace) -> None:
    if args.command == "evaluate":
        await _evaluate(args)
        return
    await _calibrate(args)


def main() -> None:
    args = _parser().parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
