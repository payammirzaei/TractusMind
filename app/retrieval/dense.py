from collections.abc import Sequence

from qdrant_client import AsyncQdrantClient

from app.chunking.models import KnowledgeChunk
from app.embeddings.service import DenseEmbeddingService
from app.embeddings.text import build_embedding_text
from app.retrieval.models import RetrievalHit
from app.retrieval.qdrant_store import QdrantKnowledgeStore, model_scoped_collection_name


class DenseRetrievalService:
    def __init__(
        self,
        *,
        qdrant: AsyncQdrantClient,
        collection_name: str,
        embedder: DenseEmbeddingService,
    ) -> None:
        self.embedder = embedder
        scoped_name = model_scoped_collection_name(collection_name, embedder.model_name)
        self.store = QdrantKnowledgeStore(qdrant, scoped_name)

    async def index(
        self,
        chunks: Sequence[KnowledgeChunk],
        *,
        remove_stale_source_versions: bool = False,
    ) -> int:
        if not chunks:
            return 0

        source_ids = {chunk.source_id for chunk in chunks}
        commit_shas = {chunk.commit_sha for chunk in chunks}
        if remove_stale_source_versions and (len(source_ids) != 1 or len(commit_shas) != 1):
            raise ValueError("Stale-version cleanup requires chunks from one source and one commit")

        await self.store.ensure_collection(self.embedder.dimension)
        embedding_texts = [build_embedding_text(chunk) for chunk in chunks]
        vectors = await self.embedder.embed_documents(embedding_texts)
        indexed = await self.store.upsert_chunks(
            chunks,
            vectors,
            embedding_model=self.embedder.model_name,
        )

        if remove_stale_source_versions:
            await self.store.remove_stale_source_versions(
                source_id=next(iter(source_ids)),
                current_commit_sha=next(iter(commit_shas)),
            )

        return indexed

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        score_threshold: float | None = None,
    ) -> list[RetrievalHit]:
        vector = await self.embedder.embed_query(query)
        return await self.store.dense_search(
            vector,
            limit=limit,
            score_threshold=score_threshold,
        )
