import re
from dataclasses import dataclass

from app.chunking.common import split_text_by_lines
from app.chunking.models import ChunkKind, KnowledgeChunk, make_chunk
from app.ingestion.models import RawDocument

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True)
class MarkdownSection:
    text: str
    start_line: int
    end_line: int
    section_path: list[str]


class MarkdownChunker:
    def __init__(self, max_chars: int = 6_000) -> None:
        self.max_chars = max_chars

    def chunk(self, document: RawDocument) -> list[KnowledgeChunk]:
        sections = self._sections(document.content)
        chunks: list[KnowledgeChunk] = []

        for section in sections:
            for text_range in split_text_by_lines(
                section.text,
                start_line=section.start_line,
                max_chars=self.max_chars,
                overlap_lines=3,
            ):
                chunks.append(
                    make_chunk(
                        document,
                        kind=ChunkKind.DOCUMENT_SECTION,
                        text=text_range.text,
                        start_line=text_range.start_line,
                        end_line=text_range.end_line,
                        section_path=section.section_path,
                        part=text_range.part,
                    )
                )

        return chunks

    def _sections(self, content: str) -> list[MarkdownSection]:
        lines = content.splitlines(keepends=True)
        if not lines:
            return []

        headings: list[tuple[int, int, str]] = []
        in_fence = False
        fence_token: str | None = None

        for index, line in enumerate(lines):
            fence_match = _FENCE_RE.match(line)
            if fence_match:
                token = fence_match.group(1)
                if not in_fence:
                    in_fence = True
                    fence_token = token
                elif token == fence_token:
                    in_fence = False
                    fence_token = None
                continue

            if in_fence:
                continue

            heading_match = _HEADING_RE.match(line.rstrip("\n"))
            if heading_match:
                headings.append(
                    (
                        index,
                        len(heading_match.group(1)),
                        heading_match.group(2).strip(),
                    )
                )

        if not headings:
            return [
                MarkdownSection(
                    text=content,
                    start_line=1,
                    end_line=len(lines),
                    section_path=[],
                )
            ]

        sections: list[MarkdownSection] = []
        first_heading_line = headings[0][0]
        if first_heading_line > 0:
            intro_text = "".join(lines[:first_heading_line]).strip()
            if intro_text:
                sections.append(
                    MarkdownSection(
                        text=intro_text,
                        start_line=1,
                        end_line=first_heading_line,
                        section_path=[],
                    )
                )

        heading_stack: list[tuple[int, str]] = []
        for heading_index, (line_index, level, title) in enumerate(headings):
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))

            next_line_index = (
                headings[heading_index + 1][0]
                if heading_index + 1 < len(headings)
                else len(lines)
            )
            section_text = "".join(lines[line_index:next_line_index]).strip()
            if not section_text:
                continue

            sections.append(
                MarkdownSection(
                    text=section_text,
                    start_line=line_index + 1,
                    end_line=next_line_index,
                    section_path=[item[1] for item in heading_stack],
                )
            )

        return sections
