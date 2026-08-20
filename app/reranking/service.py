import asyncio
from collections.abc import Sequence
from functools import cached_property

from fastembed.rerank.cross_encoder import TextCrossEncoder

from app.retrieval.models import RetrievalHit


class CrossEncoderReranker:
    """Rerank a small retrieval candidate set with a FastEmbed cross-encoder."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    @cached_property
    def model(self) -> TextCrossEncoder:
        return TextCrossEncoder(model_name=self.model_name, lazy_load=True)

    async def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievalHit],
        *,
        limit: int = 6,
    ) -> list[RetrievalHit]:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("Query must not be empty")
        if limit < 1:
            raise ValueError("limit must be greater than zero")
        if not candidates:
            return []

        documents = [self._document_text(hit) for hit in candidates]
        scores = await asyncio.to_thread(self._score, normalized_query, documents)

        reranked = [
            hit.model_copy(
                update={
                    "score": score,
                    "retrieval_score": hit.score,
                    "rerank_score": score,
                }
            )
            for hit, score in zip(candidates, scores, strict=True)
        ]
        reranked.sort(key=lambda hit: hit.rerank_score or float("-inf"), reverse=True)
        return reranked[:limit]

    def _score(self, query: str, documents: list[str]) -> list[float]:
        return [float(score) for score in self.model.rerank(query, documents)]

    def _document_text(self, hit: RetrievalHit) -> str:
        context = [
            f"Repository: {hit.repository}",
            f"Component: {hit.component}",
            f"Path: {hit.path}",
        ]
        if hit.language:
            context.append(f"Language: {hit.language}")
        if hit.section_path:
            context.append(f"Section: {' > '.join(hit.section_path)}")
        if hit.parent_symbol and hit.symbol:
            context.append(f"Symbol: {hit.parent_symbol} > {hit.symbol}")
        elif hit.symbol:
            context.append(f"Symbol: {hit.symbol}")

        return "\n".join(context) + "\n\n" + hit.text
