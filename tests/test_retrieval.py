from app.chunking.models import ChunkKind, KnowledgeChunk
from app.embeddings.text import build_embedding_text, build_sparse_text
from app.retrieval.qdrant_store import QdrantKnowledgeStore, model_scoped_collection_name


def _chunk() -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id="chunk-1",
        document_id="doc-1",
        source_id="tractusx-sdk",
        repository="eclipse-tractusx/tractusx-sdk",
        component="sdk",
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
    assert payload["commit_sha"] == "a" * 40
    assert payload["symbol"] == "create_asset"
    assert payload["parent_symbol"] == "BaseConnectorService"
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
