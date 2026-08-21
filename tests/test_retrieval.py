import pytest

from app.chunking.models import ChunkKind, KnowledgeChunk
from app.embeddings.text import build_embedding_text, build_sparse_text
from app.retrieval.hybrid import HybridRetrievalService
from app.retrieval.qdrant_store import QdrantKnowledgeStore, model_scoped_collection_name


def _chunk() -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id="chunk-1",
        document_id="doc-1",
        source_id="tractusx-sdk",
        repository="eclipse-tractusx/tractusx-sdk",
        component="sdk",
        version_ref="v0.9.0",
        commit_sha="a" * 40,
        path="tractusx_sdk/dataspace/services/connector.py",
        blob_sha="b" * 40,
        content_type="code",
        language="python",
        kind=ChunkKind.CODE_SYMBOL,
        text="def create_asset(asset_id: str):\n    return asset_id",
        text_sha256="c" * 64,
        source_url=(
            f"https://github.com/eclipse-tractusx/tractusx-sdk/blob/{'a' * 40}/"
            "tractusx_sdk/dataspace/services/connector.py"
        ),
        start_line=120,
        end_line=121,
        symbol="create_asset",
        parent_symbol="BaseConnectorService",
        section_path=[],
        part=1,
    )


def test_embedding_text_adds_retrieval_context_without_mutating_source_text() -> None:
    chunk = _chunk()

    text = build_embedding_text(chunk)

    assert "Repository: eclipse-tractusx/tractusx-sdk" in text
    assert "Component: sdk" in text
    assert "Symbol: BaseConnectorService > create_asset" in text
    assert text.endswith(chunk.text)
    assert chunk.text == "def create_asset(asset_id: str):\n    return asset_id"


def test_sparse_text_keeps_exact_path_and_symbol_tokens() -> None:
    chunk = _chunk()

    text = build_sparse_text(chunk)

    assert "tractusx_sdk/dataspace/services/connector.py" in text
    assert "BaseConnectorService" in text
    assert "create_asset" in text
    assert text.endswith(chunk.text)


def test_qdrant_payload_keeps_exact_traceability() -> None:
    chunk = _chunk()
    store = QdrantKnowledgeStore(client=object(), collection_name="test")  # type: ignore[arg-type]

    payload = store._payload(chunk, "BAAI/bge-small-en-v1.5", "Qdrant/bm25")

    assert payload["chunk_id"] == chunk.chunk_id
    assert payload["version_ref"] == "v0.9.0"
    assert payload["snapshot_commit_sha"] == "a" * 40
    assert payload["commit_sha"] == "a" * 40
    assert payload["symbol"] == "create_asset"
    assert payload["parent_symbol"] == "BaseConnectorService"
    assert "tractusx_sdk/dataspace/services/connector.py" in payload["debug_text"]
    assert "BaseConnectorService" in payload["debug_text"]
    assert "create_asset" in payload["debug_text"]
    assert payload["line_source_url"].endswith("#L120-L121")
    assert payload["embedding_model"] == "BAAI/bge-small-en-v1.5"
    assert payload["sparse_model"] == "Qdrant/bm25"


def test_qdrant_collection_is_isolated_by_retrieval_models() -> None:
    dense = model_scoped_collection_name(
        "tractusmind_knowledge",
        "BAAI/bge-small-en-v1.5",
    )
    hybrid = model_scoped_collection_name(
        "tractusmind_knowledge",
        "BAAI/bge-small-en-v1.5",
        "Qdrant/bm25",
    )
    other_hybrid = model_scoped_collection_name(
        "tractusmind_knowledge",
        "BAAI/bge-small-en-v1.5",
        "prithivida/Splade_PP_en_v1",
    )

    assert dense.startswith("tractusmind_knowledge__")
    assert hybrid.startswith("tractusmind_knowledge__")
    assert dense != hybrid
    assert hybrid != other_hybrid
    assert hybrid == model_scoped_collection_name(
        "tractusmind_knowledge",
        "BAAI/bge-small-en-v1.5",
        "Qdrant/bm25",
    )


class _FakeDenseEmbedder:
    model_name = "dense-test"
    batch_size = 32
    dimension = 2

    def __init__(self) -> None:
        self.batch_lengths: list[int] = []

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.batch_lengths.append(len(texts))
        return [[0.1, 0.2] for _ in texts]


class _FakeSparseEmbedder:
    model_name = "sparse-test"
    batch_size = 32

    def __init__(self) -> None:
        self.batch_lengths: list[int] = []

    async def embed_documents(self, texts: list[str]) -> list[object]:
        self.batch_lengths.append(len(texts))
        return [object() for _ in texts]


class _FakeStore:
    def __init__(self) -> None:
        self.upsert_lengths: list[int] = []
        self.ensure_calls = 0

    async def ensure_collection(self, dimension: int, *, hybrid: bool) -> None:
        assert dimension == 2
        assert hybrid is True
        self.ensure_calls += 1

    async def upsert_chunks(
        self,
        chunks: list[KnowledgeChunk],
        dense_vectors: list[list[float]],
        *,
        sparse_vectors: list[object],
        embedding_model: str,
        sparse_model: str,
    ) -> int:
        assert len(chunks) == len(dense_vectors) == len(sparse_vectors)
        assert embedding_model == "dense-test"
        assert sparse_model == "sparse-test"
        self.upsert_lengths.append(len(chunks))
        return len(chunks)


@pytest.mark.asyncio
async def test_hybrid_index_bounds_repository_sized_embedding_batches() -> None:
    dense = _FakeDenseEmbedder()
    sparse = _FakeSparseEmbedder()
    store = _FakeStore()
    service = object.__new__(HybridRetrievalService)
    service.dense_embedder = dense
    service.sparse_embedder = sparse
    service.store = store

    seed = _chunk()
    chunks = [
        seed.model_copy(update={"chunk_id": f"chunk-{index}"})
        for index in range(70)
    ]

    indexed = await service.index(chunks)

    assert indexed == 70
    assert store.ensure_calls == 1
    assert dense.batch_lengths == [32, 32, 6]
    assert sparse.batch_lengths == [32, 32, 6]
    assert store.upsert_lengths == [32, 32, 6]
