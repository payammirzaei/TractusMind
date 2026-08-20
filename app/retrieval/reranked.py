from app.reranking.service import CrossEncoderReranker
from app.retrieval.hybrid import HybridRetrievalService
from app.retrieval.models import RetrievalHit
from app.routing.models import QueryRoute


class RerankedRetrievalService:
    """Production retrieval path: Hybrid first-stage retrieval + cross-encoder reranking."""

    def __init__(
        self,
        *,
        retrieval: HybridRetrievalService,
        reranker: CrossEncoderReranker,
        candidate_k: int = 20,
        prefetch_k: int = 40,
    ) -> None:
        if candidate_k < 1:
            raise ValueError("candidate_k must be greater than zero")
        if prefetch_k < candidate_k:
            raise ValueError("prefetch_k must be greater than or equal to candidate_k")

        self.retrieval = retrieval
        self.reranker = reranker
        self.candidate_k = candidate_k
        self.prefetch_k = prefetch_k

    async def search(
        self,
        query: str,
        *,
        limit: int = 6,
        route: QueryRoute | None = None,
    ) -> list[RetrievalHit]:
        if limit < 1:
            raise ValueError("limit must be greater than zero")

        candidate_k = max(self.candidate_k, limit)
        candidates = await self.retrieval.search_hybrid(
            query,
            limit=candidate_k,
            prefetch_limit=max(self.prefetch_k, candidate_k),
            route=route,
        )
        return await self.reranker.rerank(query, candidates, limit=limit)
