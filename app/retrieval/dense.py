from collections.abc import Sequence

from qdrant_client import AsyncQdrantClient

from app.chunking.models import KnowledgeChunk
from app.embeddings.service import DenseEmbeddingService
from app.embeddings.text import build_embedding_text
from app.retrieval.models import RetrievalHit
from app.retrieval.qdrant_store import QdrantKnowledgeStore


class DenseRetrievalService:
    def __init__(
        self,
        *,
        qdrant: AsyncQdrantClient,
        collection_name: str,
        embedder: DenseEmbeddingService,
    ) -> None:
        self.embedder = embedder
        self.store = QdrantKnowledgeStore(qdrant, collection_name)

    async def index(self, chunks: Sequence[KnowledgeChunk]) -> int:
        if not chunks:
            return 0

        await self.store.ensure_collection(self.embedder.dimension)
        embedding_texts = [build_embedding_text(chunk) for chunk in chunks]
        vectors = await self.embedder.embed_documents(embedding_texts)
        return await self.store.upsert_chunks(
            chunks,
            vectors,
            embedding_model=self.embedder.model_name,
        )

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        score_threshold: float | None = None,
    ) -> list[RetrievalHit]:
        vector = await self.embedder.embed_query(query)
        return await self.store.search(
            vector,
            limit=limit,
            score_threshold=score_threshold,
        )
