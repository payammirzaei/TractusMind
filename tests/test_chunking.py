from app.chunking import ChunkKind, SmartChunker
from app.ingestion.models import RawDocument


def _document(
    *,
    path: str,
    content: str,
    content_type: str,
    language: str | None,
) -> RawDocument:
    return RawDocument(
        document_id="doc-1",
        source_id="test-source",
        repository="eclipse-tractusx/test",
        component="test",
        commit_sha="a" * 40,
        path=path,
        blob_sha="b" * 40,
        content_type=content_type,
        language=language,
        content=content,
        content_sha256="c" * 64,
        source_url=f"https://github.com/eclipse-tractusx/test/blob/{'a' * 40}/{path}",
        size_bytes=len(content.encode("utf-8")),
    )


def test_markdown_chunking_preserves_heading_hierarchy() -> None:
    document = _document(
        path="docs/guide.md",
        content=(
            "# Connector\n"
            "Connector overview.\n\n"
            "## Contract Negotiation\n"
            "Negotiate a contract before transfer.\n"
        ),
        content_type="documentation",
        language="markdown",
    )

    chunks = SmartChunker().chunk(document)

    assert len(chunks) == 2
    assert chunks[0].kind == ChunkKind.DOCUMENT_SECTION
    assert chunks[0].section_path == ["Connector"]
    assert chunks[1].section_path == ["Connector", "Contract Negotiation"]
    assert chunks[1].start_line == 4


def test_python_chunking_preserves_symbol_parentage_and_decorators() -> None:
    document = _document(
        path="tractusx_sdk/service.py",
        content=(
            "@registered\n"
            "class ConnectorService:\n"
            "    def create_asset(self, asset_id: str) -> str:\n"
            "        return asset_id\n"
        ),
        content_type="code",
        language="python",
    )

    chunks = SmartChunker().chunk(document)
    class_chunk = next(chunk for chunk in chunks if chunk.symbol == "ConnectorService")
    method_chunk = next(chunk for chunk in chunks if chunk.symbol == "create_asset")

    assert class_chunk.kind == ChunkKind.CODE_SYMBOL
    assert class_chunk.parent_symbol is None
    assert class_chunk.text.startswith("@registered")
    assert method_chunk.parent_symbol == "ConnectorService"
    assert method_chunk.start_line == 3


def test_yaml_chunking_uses_top_level_keys() -> None:
    document = _document(
        path="config/application.yml",
        content=(
            "server:\n"
            "  port: 8080\n"
            "connector:\n"
            "  managementPath: /management\n"
        ),
        content_type="configuration",
        language="yaml",
    )

    chunks = SmartChunker().chunk(document)

    assert [chunk.symbol for chunk in chunks] == ["server", "connector"]
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 2
    assert chunks[1].start_line == 3
    assert chunks[1].end_line == 4


def test_chunk_ids_are_stable_for_same_document() -> None:
    document = _document(
        path="README.md",
        content="# Title\nSame content\n",
        content_type="documentation",
        language="markdown",
    )
    chunker = SmartChunker()

    first = chunker.chunk(document)
    second = chunker.chunk(document)

    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
