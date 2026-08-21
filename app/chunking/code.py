from collections.abc import Iterator
from dataclasses import dataclass

from tree_sitter import Node
from tree_sitter_language_pack import get_parser

from app.chunking.common import split_text_by_lines
from app.chunking.models import ChunkKind, KnowledgeChunk, make_chunk
from app.ingestion.models import RawDocument

_SUPPORTED_LANGUAGES = {"python", "java", "kotlin", "typescript", "javascript"}

_DECLARATION_TYPES: dict[str, set[str]] = {
    "python": {"class_definition", "function_definition"},
    "java": {
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "record_declaration",
        "method_declaration",
        "constructor_declaration",
    },
    "kotlin": {
        "class_declaration",
        "object_declaration",
        "function_declaration",
        "secondary_constructor",
    },
    "typescript": {
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "function_declaration",
        "method_definition",
        "type_alias_declaration",
    },
    "javascript": {
        "class_declaration",
        "function_declaration",
        "method_definition",
    },
}

_CLASS_LIKE_TYPES = {
    "class_definition",
    "class_declaration",
    "interface_declaration",
    "enum_declaration",
    "record_declaration",
    "object_declaration",
}

_METHOD_LIKE_TYPES = {
    "function_definition",
    "function_declaration",
    "method_declaration",
    "constructor_declaration",
    "method_definition",
    "secondary_constructor",
}


@dataclass(frozen=True)
class _DeclarationSnapshot:
    """Pure-Python declaration data detached from native tree-sitter nodes."""

    symbol: str
    parent_symbol: str | None
    text: str
    start_line: int


class CodeChunker:
    def __init__(self, max_chars: int = 8_000) -> None:
        self.max_chars = max_chars

    def supports(self, language: str | None) -> bool:
        return language in _SUPPORTED_LANGUAGES

    def chunk(self, document: RawDocument) -> list[KnowledgeChunk]:
        language = document.language
        if language not in _SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported code language: {language}")

        source_bytes = document.content.encode("utf-8")
        parser = get_parser(language)
        tree = parser.parse(source_bytes)

        # Do not retain tree-sitter Node objects after traversal. Some native
        # parser/language-pack combinations can invalidate retained child/parent
        # handles while Python later materializes chunks, causing an uncatchable
        # SIGSEGV. Snapshot all required data while the tree is unquestionably
        # alive, then build KnowledgeChunk objects from plain Python values.
        declarations = list(
            self._walk_declarations(tree.root_node, language, source_bytes)
        )
        del tree
        del parser

        if not declarations:
            return self._fallback_document_chunk(document)

        chunks: list[KnowledgeChunk] = []
        for declaration in declarations:
            ranges = split_text_by_lines(
                declaration.text,
                start_line=declaration.start_line,
                max_chars=self.max_chars,
                overlap_lines=4,
            )
            for text_range in ranges:
                chunks.append(
                    make_chunk(
                        document,
                        kind=ChunkKind.CODE_SYMBOL,
                        text=text_range.text,
                        start_line=text_range.start_line,
                        end_line=text_range.end_line,
                        symbol=declaration.symbol,
                        parent_symbol=declaration.parent_symbol,
                        part=text_range.part,
                    )
                )

        chunks.sort(key=lambda chunk: (chunk.start_line, chunk.end_line, chunk.symbol or ""))
        return self._deduplicate(chunks)

    def _walk_declarations(
        self,
        node: Node,
        language: str,
        source_bytes: bytes,
        parent_symbol: str | None = None,
    ) -> Iterator[_DeclarationSnapshot]:
        declaration_types = _DECLARATION_TYPES[language]
        current_parent = parent_symbol

        if node.type in declaration_types:
            symbol = self._symbol_name(node, source_bytes)
            if symbol:
                effective_node = self._include_python_decorators(node, language)
                node_text = source_bytes[
                    effective_node.start_byte : effective_node.end_byte
                ].decode("utf-8")
                start_line = effective_node.start_point.row + 1

                if node.type in _CLASS_LIKE_TYPES and len(node_text) > self.max_chars:
                    node_text = self._class_context_text(
                        effective_node,
                        source_bytes,
                        language,
                    )

                yield _DeclarationSnapshot(
                    symbol=symbol,
                    parent_symbol=parent_symbol,
                    text=node_text,
                    start_line=start_line,
                )
                if node.type in _CLASS_LIKE_TYPES or node.type in _METHOD_LIKE_TYPES:
                    current_parent = symbol

        for child in node.children:
            yield from self._walk_declarations(
                child,
                language,
                source_bytes,
                parent_symbol=current_parent,
            )

    def _symbol_name(self, node: Node, source_bytes: bytes) -> str | None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            for child in node.children:
                if child.type in {"identifier", "type_identifier", "simple_identifier"}:
                    name_node = child
                    break
        if name_node is None:
            return None
        return source_bytes[name_node.start_byte : name_node.end_byte].decode("utf-8").strip()

    def _include_python_decorators(self, node: Node, language: str) -> Node:
        if (
            language == "python"
            and node.parent is not None
            and node.parent.type == "decorated_definition"
        ):
            return node.parent
        return node

    def _class_context_text(self, node: Node, source_bytes: bytes, language: str) -> str:
        method_types = _DECLARATION_TYPES[language] & _METHOD_LIKE_TYPES
        first_method = self._first_member(node, method_types)
        end_byte = first_method.start_byte if first_method is not None else node.end_byte
        context = source_bytes[node.start_byte:end_byte].decode("utf-8").strip()

        if len(context) >= 200:
            return context[: self.max_chars]

        full_text = source_bytes[node.start_byte : node.end_byte].decode("utf-8")
        return full_text[: self.max_chars]

    def _first_member(self, node: Node, target_types: set[str]) -> Node | None:
        for child in node.children:
            if child.type in target_types:
                return child
        for child in node.children:
            for grandchild in child.children:
                if grandchild.type in target_types:
                    return grandchild
        return None

    def _fallback_document_chunk(self, document: RawDocument) -> list[KnowledgeChunk]:
        chunks: list[KnowledgeChunk] = []
        for text_range in split_text_by_lines(
            document.content,
            start_line=1,
            max_chars=self.max_chars,
            overlap_lines=4,
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

    def _deduplicate(self, chunks: list[KnowledgeChunk]) -> list[KnowledgeChunk]:
        seen: set[tuple[int, int, str | None, str]] = set()
        result: list[KnowledgeChunk] = []
        for chunk in chunks:
            key = (chunk.start_line, chunk.end_line, chunk.symbol, chunk.text_sha256)
            if key in seen:
                continue
            seen.add(key)
            result.append(chunk)
        return result
