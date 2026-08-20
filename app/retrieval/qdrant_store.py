import hashlib
import uuid
from collections.abc import Sequence

from qdrant_client import AsyncQdrantClient, models

from app.chunking.models import KnowledgeChunk
from app.retrieval.models import RetrievalHit

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "bm25"


def model_scoped_collection_name(
    base_name: str,
    embedding_model: str,
    sparse_model: str | None = None,
) -> str:
    identity = embedding_model if sparse_model is None else f"{embedding_model}|{sparse_model}"
    model_hash = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    return f"{base_name}__{model_hash}"


class QdrantKnowledgeStore:
    def __init__(self, client: AsyncQdrantClient, collection_name: str) -> None:
        self.client = client
        self.collection_name = collection_name

    async def ensure_collection(self, dimension: int, *, hybrid: bool = False) -> None:
        exists = await self.client.collection_exists(self.collection_name)
        if exists:
            return

        sparse_config = None
        if hybrid:
            sparse_config = {
                SPARSE_VECTOR_NAME: models.SparseVectorParams(modifier=models.Modifier.IDF)
            }

        await self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config={
                DENSE_VECTOR_NAME: models.VectorParams(
                    size=dimension,
                    distance=models.Distance.COSINE,
                )
            },
            sparse_vectors_config=sparse_config,
        )

        for field in (
            "source_id",
            "repository",
            "component",
            "commit_sha",
            "content_type",
            "language",
            "kind",
            "path",
        ):
            await self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD,
                wait=True,
            )

    async def upsert_chunks(
        self,
        chunks: Sequence[KnowledgeChunk],
        dense_vectors: Sequence[Sequence[float]],
        *,
        embedding_model: str,
        sparse_vectors: Sequence[models.SparseVector] | None = None,
        sparse_model: str | None = None,
        batch_size: int = 128,
    ) -> int:
        if len(chunks) != len(dense_vectors):
            raise ValueError("chunks and dense_vectors must have the same length")
        if sparse_vectors is not None and len(chunks) != len(sparse_vectors):
            raise ValueError("chunks and sparse_vectors must have the same length")

        indexed = 0
        for start in range(0, len(chunks), batch_size):
            batch_chunks = chunks[start : start + batch_size]
            batch_dense = dense_vectors[start : start + batch_size]
            batch_sparse = sparse_vectors[start : start + batch_size] if sparse_vectors else None

            points: list[models.PointStruct] = []
            for offset, (chunk, dense_vector) in enumerate(
                zip(batch_chunks, batch_dense, strict=True)
            ):
                vectors: dict[str, object] = {DENSE_VECTOR_NAME: list(dense_vector)}
                if batch_sparse is not None:
                    vectors[SPARSE_VECTOR_NAME] = batch_sparse[offset]

                points.append(
                    models.PointStruct(
                        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"tractusmind:{chunk.chunk_id}")),
                        vector=vectors,
                        payload=self._payload(chunk, embedding_model, sparse_model),
                    )
                )

            await self.client.upsert(
                collection_name=self.collection_name,
                points=points,
                wait=True,
            )
            indexed += len(points)

        return indexed

    async def remove_stale_source_versions(self, source_id: str, current_commit_sha: str) -> None:
        await self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="source_id",
                            match=models.MatchValue(value=source_id),
                        )
                    ],
                    must_not=[
                        models.FieldCondition(
                            key="commit_sha",
                            match=models.MatchValue(value=current_commit_sha),
                        )
                    ],
                )
            ),
            wait=True,
        )

    async def dense_search(
        self,
        query_vector: Sequence[float],
        *,
        limit: int = 10,
        query_filter: models.Filter | None = None,
        score_threshold: float | None = None,
    ) -> list[RetrievalHit]:
        result = await self.client.query_points(
            collection_name=self.collection_name,
            query=list(query_vector),
            using=DENSE_VECTOR_NAME,
            query_filter=query_filter,
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
        )
        return self._hits(result.points)

    async def hybrid_search(
        self,
        dense_vector: Sequence[float],
        sparse_vector: models.SparseVector,
        *,
        limit: int = 10,
        prefetch_limit: int = 40,
        query_filter: models.Filter | None = None,
    ) -> list[RetrievalHit]:
        result = await self.client.query_points(
            collection_name=self.collection_name,
            prefetch=[
                models.Prefetch(
                    query=list(dense_vector),
                    using=DENSE_VECTOR_NAME,
                    limit=prefetch_limit,
                ),
                models.Prefetch(
                    query=sparse_vector,
                    using=SPARSE_VECTOR_NAME,
                    limit=prefetch_limit,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        return self._hits(result.points)

    def _hits(self, points: Sequence[object]) -> list[RetrievalHit]:
        hits: list[RetrievalHit] = []
        for point in points:
            payload = point.payload or {}  # type: ignore[attr-defined]
            hits.append(
                RetrievalHit(
                    chunk_id=str(payload["chunk_id"]),
                    score=float(point.score),  # type: ignore[attr-defined]
                    text=str(payload["text"]),
                    source_id=str(payload["source_id"]),
                    repository=str(payload["repository"]),
                    component=str(payload["component"]),
                    commit_sha=str(payload["commit_sha"]),
                    path=str(payload["path"]),
                    content_type=str(payload["content_type"]),
                    language=(str(payload["language"]) if payload.get("language") else None),
                    kind=str(payload["kind"]),
                    start_line=int(payload["start_line"]),
                    end_line=int(payload["end_line"]),
                    symbol=(str(payload["symbol"]) if payload.get("symbol") else None),
                    parent_symbol=(
                        str(payload["parent_symbol"]) if payload.get("parent_symbol") else None
                    ),
                    section_path=[str(item) for item in payload.get("section_path", [])],
                    source_url=str(payload["line_source_url"]),
                )
            )
        return hits

    def _payload(
        self,
        chunk: KnowledgeChunk,
        embedding_model: str,
        sparse_model: str | None = None,
    ) -> dict[str, object]:
        return {
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "source_id": chunk.source_id,
            "repository": chunk.repository,
            "component": chunk.component,
            "commit_sha": chunk.commit_sha,
            "path": chunk.path,
            "blob_sha": chunk.blob_sha,
            "content_type": chunk.content_type,
            "language": chunk.language,
            "kind": chunk.kind.value,
            "text": chunk.text,
            "text_sha256": chunk.text_sha256,
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
            "symbol": chunk.symbol,
            "parent_symbol": chunk.parent_symbol,
            "section_path": chunk.section_path,
            "part": chunk.part,
            "source_url": chunk.source_url,
            "line_source_url": chunk.line_source_url,
            "embedding_model": embedding_model,
            "sparse_model": sparse_model,
        }
