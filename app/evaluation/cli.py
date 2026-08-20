import argparse
import asyncio
import json
from pathlib import Path

from app.core.config import Settings, get_settings
from app.embeddings.service import DenseEmbeddingService
from app.embeddings.sparse import SparseEmbeddingService
from app.evaluation.benchmark import aggregate_metrics, evaluate_case, load_benchmark
from app.infra.qdrant import create_qdrant_client
from app.reranking.service import CrossEncoderReranker
from app.retrieval.hybrid import HybridRetrievalService
from app.retrieval.reranked import RerankedRetrievalService


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tractusmind-benchmark")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("benchmarks/dense_v0.jsonl"),
    )
    parser.add_argument(
        "--mode",
        choices=("dense", "hybrid", "rerank", "all"),
        default="all",
    )
    parser.add_argument("--k", type=int, default=5)
    return parser


def _services(settings: Settings):
    qdrant = create_qdrant_client(settings)
    retrieval = HybridRetrievalService(
        qdrant=qdrant,
        collection_name=settings.qdrant_collection,
        dense_embedder=DenseEmbeddingService(
            settings.embedding_model,
            batch_size=settings.embedding_batch_size,
        ),
        sparse_embedder=SparseEmbeddingService(
            settings.sparse_embedding_model,
            batch_size=settings.sparse_embedding_batch_size,
        ),
    )
    reranked = RerankedRetrievalService(
        retrieval=retrieval,
        reranker=CrossEncoderReranker(
            settings.reranker_model,
            batch_size=settings.reranker_batch_size,
        ),
        candidate_k=settings.retrieval_top_k,
        prefetch_k=max(settings.hybrid_prefetch_k, settings.retrieval_top_k),
    )
    return qdrant, retrieval, reranked


async def _search_mode(
    retrieval: HybridRetrievalService,
    reranked: RerankedRetrievalService,
    question: str,
    mode: str,
    k: int,
    settings: Settings,
):
    if mode == "dense":
        return await retrieval.search_dense(question, limit=k)
    if mode == "hybrid":
        return await retrieval.search_hybrid(
            question,
            limit=k,
            prefetch_limit=settings.hybrid_prefetch_k,
        )
    return await reranked.search(question, limit=k)


async def _run_mode(
    retrieval: HybridRetrievalService,
    reranked: RerankedRetrievalService,
    cases,
    mode: str,
    k: int,
    settings: Settings,
):
    evaluations = []
    details = []
    for case in cases:
        hits = await _search_mode(
            retrieval,
            reranked,
            case.question,
            mode,
            k,
            settings,
        )
        metrics = evaluate_case(case, hits, k)
        evaluations.append(metrics)
        details.append(
            {
                "id": case.id,
                "category": case.category,
                "hit": bool(metrics[0]),
                "first_relevant_rank": next(
                    (
                        rank
                        for rank, hit in enumerate(hits[:k], start=1)
                        if evaluate_case(case, [hit], 1)[0]
                    ),
                    None,
                ),
                "top_sources": [hit.source_id for hit in hits[:k]],
            }
        )

    summary = aggregate_metrics(evaluations)
    return {
        "mode": mode,
        "k": k,
        "cases": summary.cases,
        "recall_at_k": round(summary.recall_at_k, 6),
        "mrr": round(summary.mrr, 6),
        "ndcg_at_k": round(summary.ndcg_at_k, 6),
        "details": details,
    }


async def _run(args: argparse.Namespace) -> None:
    settings = get_settings()
    cases = load_benchmark(args.dataset)
    qdrant, retrieval, reranked = _services(settings)
    modes = ("dense", "hybrid", "rerank") if args.mode == "all" else (args.mode,)
    try:
        reports = [
            await _run_mode(
                retrieval,
                reranked,
                cases,
                mode,
                args.k,
                settings,
            )
            for mode in modes
        ]
    finally:
        await qdrant.close()

    print(
        json.dumps(
            {
                "dataset": str(args.dataset),
                "dense_model": settings.embedding_model,
                "sparse_model": settings.sparse_embedding_model,
                "reranker_model": settings.reranker_model,
                "candidate_k": settings.retrieval_top_k,
                "reports": reports,
            },
            indent=2,
        )
    )


def main() -> None:
    args = _parser().parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
