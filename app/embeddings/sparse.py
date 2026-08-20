import asyncio
from collections.abc import Sequence
from functools import cached_property

from fastembed import SparseTextEmbedding
from qdrant_client import models


class SparseEmbeddingService:
    """Local BM25-style sparse embeddings for lexical/exact-match retrieval."""

    def __init__(self, model_name: str = "Qdrant/bm25", *, batch_size: int = 32) -> None:
        self.model_name = model_name
        self.batch_size = batch_size

    @cached_property
    def model(self) -> SparseTextEmbedding:
        return SparseTextEmbedding(model_name=self.model_name)

    async def embed_documents(self, texts: Sequence[str]) -> list[models.SparseVector]:
        if not texts:
            return []
        return await asyncio.to_thread(self._encode, list(texts))

    async def embed_query(self, query: str) -> models.SparseVector:
        normalized = query.strip()
        if not normalized:
            raise ValueError("Query must not be empty")
        vectors = await asyncio.to_thread(self._encode, [normalized])
        return vectors[0]

    def _encode(self, texts: list[str]) -> list[models.SparseVector]:
        embeddings = self.model.embed(texts, batch_size=self.batch_size)
        return [
            models.SparseVector(
                indices=embedding.indices.astype("uint32").tolist(),
                values=embedding.values.astype("float32").tolist(),
            )
            for embedding in embeddings
        ]
