from app.chunking.code import CodeChunker
from app.chunking.common import split_text_by_lines
from app.chunking.markdown import MarkdownChunker
from app.chunking.models import ChunkKind, KnowledgeChunk, make_chunk
from app.chunking.structured import StructuredChunker
from app.ingestion.models import RawDocument


class SmartChunker:
    def __init__(
        self,
        *,
        documentation_max_chars: int = 6_000,
        code_max_chars: int = 8_000,
        structured_max_chars: int = 6_000,
    ) -> None:
        self.markdown = MarkdownChunker(max_chars=documentation_max_chars)
        self.code = CodeChunker(max_chars=code_max_chars)
        self.structured = StructuredChunker(max_chars=structured_max_chars)
        self.fallback_max_chars = documentation_max_chars

    def chunk(self, document: RawDocument) -> list[KnowledgeChunk]:
        if document.content_type == "documentation" or document.language == "markdown":
            return self.markdown.chunk(document)

        if document.content_type == "code":
            if self.code.supports(document.language):
                return self.code.chunk(document)
            return self._fallback(document)

        if document.content_type in {
            "structured_data",
            "configuration",
            "semantic_model",
        }:
            return self.structured.chunk(document)

        return self._fallback(document)

    def chunk_many(self, documents: list[RawDocument]) -> list[KnowledgeChunk]:
        chunks: list[KnowledgeChunk] = []
        for document in documents:
            chunks.extend(self.chunk(document))
        return chunks

    def _fallback(self, document: RawDocument) -> list[KnowledgeChunk]:
        chunks: list[KnowledgeChunk] = []
        for text_range in split_text_by_lines(
            document.content,
            start_line=1,
            max_chars=self.fallback_max_chars,
            overlap_lines=3,
        ):
            chunks.append(
                make_chunk(
                    document,
                    kind=ChunkKind.TEXT,
                    text=text_range.text,
                    start_line=text_range.start_line,
                    end_line=text_range.end_line,
                    part=text_range.part,
                )
            )
        return chunks
