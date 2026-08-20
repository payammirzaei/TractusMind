import asyncio
from collections.abc import Sequence
from functools import cached_property
from time import perf_counter

from fastembed import SparseTextEmbedding
from qdrant_client import models

from app.observability.metrics import MODEL_OPERATION_DURATION, record_model_load


class SparseEmbeddingService:
    """Local BM25-style sparse embeddings for lexical/exact-match retrieval."""

    def __init__(self, model_name: str = "Qdrant/bm25", *, batch_size: int = 32) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self._warmed = False

    @cached_property
    def model(self) -> SparseTextEmbedding:
        return SparseTextEmbedding(model_name=self.model_name)

    async def embed_documents(self, texts: Sequence[str]) -> list[models.SparseVector]:
        if not texts:
            return []
        return await self._run("documents", list(texts))

    async def embed_query(self, query: str) -> models.SparseVector:
        normalized = query.strip()
        if not normalized:
            raise ValueError("Query must not be empty")
        vectors = await self._run("query", [normalized])
        return vectors[0]

    async def _run(self, operation: str, texts: list[str]) -> list[models.SparseVector]:
        started = perf_counter()
        result = await asyncio.to_thread(self._encode, texts)
        duration = perf_counter() - started
        MODEL_OPERATION_DURATION.labels(role="sparse", operation=operation).observe(duration)
        if not self._warmed:
            record_model_load("sparse", duration)
            self._warmed = True
        return result

    def _encode(self, texts: list[str]) -> list[models.SparseVector]:
        embeddings = self.model.embed(texts, batch_size=self.batch_size)
        return [
            models.SparseVector(
                indices=embedding.indices.astype("uint32").tolist(),
                values=embedding.values.astype("float32").tolist(),
            )
            for embedding in embeddings
        ]
