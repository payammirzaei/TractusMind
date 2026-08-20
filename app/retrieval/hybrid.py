from collections.abc import Sequence

from qdrant_client import AsyncQdrantClient

from app.chunking.models import KnowledgeChunk
from app.embeddings.service import DenseEmbeddingService
from app.embeddings.sparse import SparseEmbeddingService
from app.embeddings.text import build_embedding_text, build_sparse_text
from app.retrieval.models import RetrievalHit
from app.retrieval.qdrant_store import QdrantKnowledgeStore, model_scoped_collection_name


class HybridRetrievalService:
    def __init__(
        self,
        *,
        qdrant: AsyncQdrantClient,
        collection_name: str,
        dense_embedder: DenseEmbeddingService,
        sparse_embedder: SparseEmbeddingService,
    ) -> None:
        self.dense_embedder = dense_embedder
        self.sparse_embedder = sparse_embedder
        scoped_name = model_scoped_collection_name(
            collection_name,
            dense_embedder.model_name,
            sparse_embedder.model_name,
        )
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

        await self.store.ensure_collection(self.dense_embedder.dimension, hybrid=True)
        dense_texts = [build_embedding_text(chunk) for chunk in chunks]
        sparse_texts = [build_sparse_text(chunk) for chunk in chunks]
        dense_vectors = await self.dense_embedder.embed_documents(dense_texts)
        sparse_vectors = await self.sparse_embedder.embed_documents(sparse_texts)
        indexed = await self.store.upsert_chunks(
            chunks,
            dense_vectors,
            sparse_vectors=sparse_vectors,
            embedding_model=self.dense_embedder.model_name,
            sparse_model=self.sparse_embedder.model_name,
        )

        if remove_stale_source_versions:
            await self.store.remove_stale_source_versions(
                source_id=next(iter(source_ids)),
                current_commit_sha=next(iter(commit_shas)),
            )

        return indexed

    async def search_dense(self, query: str, *, limit: int = 10) -> list[RetrievalHit]:
        dense_vector = await self.dense_embedder.embed_query(query)
        return await self.store.dense_search(dense_vector, limit=limit)

    async def search_hybrid(
        self,
        query: str,
        *,
        limit: int = 10,
        prefetch_limit: int = 40,
    ) -> list[RetrievalHit]:
        dense_vector = await self.dense_embedder.embed_query(query)
        sparse_vector = await self.sparse_embedder.embed_query(query)
        return await self.store.hybrid_search(
            dense_vector,
            sparse_vector,
            limit=limit,
            prefetch_limit=max(prefetch_limit, limit),
        )
