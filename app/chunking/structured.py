import re

from app.chunking.common import split_text_by_lines
from app.chunking.models import ChunkKind, KnowledgeChunk, make_chunk
from app.ingestion.models import RawDocument

_YAML_TOP_LEVEL_RE = re.compile(r"^([A-Za-z0-9_.-]+)\s*:")
_TTL_PREFIX_RE = re.compile(r"^\s*(?:@prefix|PREFIX)\b", re.IGNORECASE)


class StructuredChunker:
    def __init__(self, max_chars: int = 6_000) -> None:
        self.max_chars = max_chars

    def chunk(self, document: RawDocument) -> list[KnowledgeChunk]:
        if document.language == "turtle" or document.content_type == "semantic_model":
            return self._chunk_turtle(document)
        if document.language == "yaml":
            return self._chunk_yaml(document)
        return self._chunk_blocks(document)

    def _chunk_yaml(self, document: RawDocument) -> list[KnowledgeChunk]:
        lines = document.content.splitlines(keepends=True)
        starts: list[tuple[int, str]] = []

        for index, line in enumerate(lines):
            if line.startswith((" ", "\t", "-")):
                continue
            match = _YAML_TOP_LEVEL_RE.match(line.rstrip("\n"))
            if match:
                starts.append((index, match.group(1)))

        if not starts:
            return self._chunk_blocks(document)

        chunks: list[KnowledgeChunk] = []
        for item_index, (start, key) in enumerate(starts):
            end = starts[item_index + 1][0] if item_index + 1 < len(starts) else len(lines)
            text = "".join(lines[start:end]).strip()
            for text_range in split_text_by_lines(
                text,
                start_line=start + 1,
                max_chars=self.max_chars,
                overlap_lines=2,
            ):
                chunks.append(
                    make_chunk(
                        document,
                        kind=ChunkKind.STRUCTURED_OBJECT,
                        text=text_range.text,
                        start_line=text_range.start_line,
                        end_line=text_range.end_line,
                        symbol=key,
                        part=text_range.part,
                    )
                )
        return chunks

    def _chunk_turtle(self, document: RawDocument) -> list[KnowledgeChunk]:
        lines = document.content.splitlines(keepends=True)
        prefix_lines: list[str] = []
        prefix_start_line: int | None = None

        chunks: list[KnowledgeChunk] = []
        statement_start: int | None = None
        statement_lines: list[str] = []
        part = 1

        for index, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            if _TTL_PREFIX_RE.match(line):
                if prefix_start_line is None:
                    prefix_start_line = index + 1
                prefix_lines.append(line.rstrip("\n"))
                continue

            if statement_start is None:
                statement_start = index
            statement_lines.append(line)

            if stripped.endswith("."):
                statement = "".join(statement_lines).strip()
                prefix_context = "\n".join(prefix_lines)
                text = f"{prefix_context}\n\n{statement}" if prefix_context else statement
                chunk_start_line = prefix_start_line or statement_start + 1
                if len(text) <= self.max_chars:
                    symbol = statement.split(maxsplit=1)[0] if statement else None
                    chunks.append(
                        make_chunk(
                            document,
                            kind=ChunkKind.SEMANTIC_ENTITY,
                            text=text,
                            start_line=chunk_start_line,
                            end_line=index + 1,
                            symbol=symbol,
                            part=part,
                        )
                    )
                    part += 1
                else:
                    for text_range in split_text_by_lines(
                        statement,
                        start_line=statement_start + 1,
                        max_chars=self.max_chars,
                        overlap_lines=2,
                    ):
                        chunks.append(
                            make_chunk(
                                document,
                                kind=ChunkKind.SEMANTIC_ENTITY,
                                text=(
                                    f"{prefix_context}\n\n{text_range.text}"
                                    if prefix_context
                                    else text_range.text
                                ),
                                start_line=prefix_start_line or text_range.start_line,
                                end_line=text_range.end_line,
                                part=text_range.part,
                            )
                        )
                statement_start = None
                statement_lines = []

        if statement_lines and statement_start is not None:
            trailing = "".join(statement_lines).strip()
            prefix_context = "\n".join(prefix_lines)
            chunks.append(
                make_chunk(
                    document,
                    kind=ChunkKind.SEMANTIC_ENTITY,
                    text=f"{prefix_context}\n\n{trailing}" if prefix_context else trailing,
                    start_line=prefix_start_line or statement_start + 1,
                    end_line=len(lines),
                )
            )

        return chunks or self._chunk_blocks(document)

    def _chunk_blocks(self, document: RawDocument) -> list[KnowledgeChunk]:
        chunks: list[KnowledgeChunk] = []
        for text_range in split_text_by_lines(
            document.content,
            start_line=1,
            max_chars=self.max_chars,
            overlap_lines=2,
        ):
            chunks.append(
                make_chunk(
                    document,
                    kind=ChunkKind.STRUCTURED_OBJECT,
                    text=text_range.text,
                    start_line=text_range.start_line,
                    end_line=text_range.end_line,
                    part=text_range.part,
                )
            )
        return chunks
