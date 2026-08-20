import asyncio
from collections.abc import Sequence
from functools import cached_property

from fastembed import TextEmbedding


class DenseEmbeddingService:
    """FastEmbed-backed dense embeddings with asymmetric retrieval semantics."""

    def __init__(
        self,
        model_name: str,
        *,
        batch_size: int = 32,
    ) -> None:
        self.model_name = model_name
        self.batch_size = batch_size

    @cached_property
    def model(self) -> TextEmbedding:
        return TextEmbedding(model_name=self.model_name, lazy_load=True)

    @cached_property
    def dimension(self) -> int:
        return int(TextEmbedding.get_embedding_size(self.model_name))

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        return await asyncio.to_thread(self._embed_documents, list(texts))

    async def embed_query(self, query: str) -> list[float]:
        normalized = query.strip()
        if not normalized:
            raise ValueError("Query must not be empty")
        return await asyncio.to_thread(self._embed_query, normalized)

    def _embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [
            vector.astype("float32").tolist()
            for vector in self.model.passage_embed(texts, batch_size=self.batch_size)
        ]

    def _embed_query(self, query: str) -> list[float]:
        vector = next(iter(self.model.query_embed(query)))
        return vector.astype("float32").tolist()
