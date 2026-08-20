import asyncio
from collections.abc import Sequence
from functools import cached_property

from sentence_transformers import SentenceTransformer


class DenseEmbeddingService:
    """Model-backed dense embeddings with separate query/document semantics."""

    def __init__(
        self,
        model_name: str,
        *,
        query_prefix: str = "Represent this sentence for searching relevant passages: ",
        batch_size: int = 32,
        device: str | None = None,
    ) -> None:
        self.model_name = model_name
        self.query_prefix = query_prefix
        self.batch_size = batch_size
        self.device = device

    @cached_property
    def model(self) -> SentenceTransformer:
        return SentenceTransformer(self.model_name, device=self.device)

    @property
    def dimension(self) -> int:
        dimension = self.model.get_sentence_embedding_dimension()
        if dimension is None:
            raise RuntimeError(f"Embedding dimension unavailable for model: {self.model_name}")
        return int(dimension)

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        return await asyncio.to_thread(self._encode, list(texts))

    async def embed_query(self, query: str) -> list[float]:
        normalized = query.strip()
        if not normalized:
            raise ValueError("Query must not be empty")
        text = f"{self.query_prefix}{normalized}" if self.query_prefix else normalized
        vectors = await asyncio.to_thread(self._encode, [text])
        return vectors[0]

    def _encode(self, texts: list[str]) -> list[list[float]]:
        embeddings = self.model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return embeddings.astype("float32").tolist()
