import ast
from collections.abc import Iterator
from dataclasses import dataclass

from tree_sitter import Node
from tree_sitter_language_pack import get_parser

from app.chunking.common import split_text_by_lines
from app.chunking.models import ChunkKind, KnowledgeChunk, make_chunk
from app.ingestion.models import RawDocument

_SUPPORTED_LANGUAGES = {"python", "java", "kotlin", "typescript", "javascript"}

_DECLARATION_TYPES: dict[str, set[str]] = {
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
    "class_declaration",
    "interface_declaration",
    "enum_declaration",
    "record_declaration",
    "object_declaration",
}

_METHOD_LIKE_TYPES = {
    "function_declaration",
    "method_declaration",
    "constructor_declaration",
    "method_definition",
    "secondary_constructor",
}

_PYTHON_DECLARATION_TYPES = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
_PYTHON_METHOD_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)


@dataclass(frozen=True)
class _DeclarationSnapshot:
    """Declaration data detached from parser-specific node objects."""

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

        if language == "python":
            declarations = self._python_declarations(document.content)
        else:
            # Tractus-X contains real-world Java/Kotlin/TypeScript/JavaScript
            # sources that can terminate the interpreter inside native
            # tree-sitter grammars. SIGSEGV cannot be caught by Python, so
            # production ingestion uses deterministic line-bounded chunks for
            # these languages. Source text, stable IDs, and exact line
            # provenance are preserved while removing the native crash surface.
            return self._safe_code_chunks(document)

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

        chunks.sort(
            key=lambda chunk: (
                chunk.start_line,
                chunk.end_line,
                chunk.symbol or "",
            )
        )
        return self._deduplicate(chunks)

    def _python_declarations(self, source: str) -> list[_DeclarationSnapshot]:
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError, TypeError, MemoryError):
            return []

        source_lines = source.splitlines(keepends=True)
        return list(
            self._walk_python_declarations(
                tree,
                source_lines,
                parent_symbol=None,
            )
        )

    def _walk_python_declarations(
        self,
        node: ast.AST,
        source_lines: list[str],
        parent_symbol: str | None,
    ) -> Iterator[_DeclarationSnapshot]:
        current_parent = parent_symbol

        if isinstance(node, _PYTHON_DECLARATION_TYPES):
            snapshot = self._snapshot_python_declaration(
                node,
                source_lines,
                parent_symbol,
            )
            yield snapshot
            current_parent = node.name

        for child in ast.iter_child_nodes(node):
            yield from self._walk_python_declarations(
                child,
                source_lines,
                current_parent,
            )

    def _snapshot_python_declaration(
        self,
        node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
        source_lines: list[str],
        parent_symbol: str | None,
    ) -> _DeclarationSnapshot:
        decorator_lines = [
            decorator.lineno
            for decorator in node.decorator_list
            if getattr(decorator, "lineno", None) is not None
        ]
        start_line = min([node.lineno, *decorator_lines])
        end_line = node.end_lineno or node.lineno
        text = "".join(source_lines[start_line - 1 : end_line])

        if isinstance(node, ast.ClassDef) and len(text) > self.max_chars:
            text = self._python_class_context_text(
                node,
                source_lines,
                start_line=start_line,
                end_line=end_line,
                full_text=text,
            )

        return _DeclarationSnapshot(
            symbol=node.name,
            parent_symbol=parent_symbol,
            text=text,
            start_line=start_line,
        )

    def _python_class_context_text(
        self,
        node: ast.ClassDef,
        source_lines: list[str],
        *,
        start_line: int,
        end_line: int,
        full_text: str,
    ) -> str:
        first_method = next(
            (member for member in node.body if isinstance(member, _PYTHON_METHOD_TYPES)),
            None,
        )
        context_end_line = (
            max(start_line, first_method.lineno - 1)
            if first_method is not None
            else end_line
        )
        context = "".join(
            source_lines[start_line - 1 : context_end_line]
        ).strip()
        if len(context) >= 200:
            return context[: self.max_chars]
        return full_text[: self.max_chars]

    def _tree_sitter_declarations(
        self,
        source: str,
        language: str,
    ) -> list[_DeclarationSnapshot]:
        source_bytes = source.encode("utf-8")
        parser = get_parser(language)
        tree = parser.parse(source_bytes)
        declarations = list(
            self._walk_tree_sitter_declarations(
                tree.root_node,
                language,
                source_bytes,
            )
        )
        del tree
        del parser
        return declarations

    def _walk_tree_sitter_declarations(
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
                node_text = source_bytes[node.start_byte : node.end_byte].decode("utf-8")
                start_line = node.start_point.row + 1

                if node.type in _CLASS_LIKE_TYPES and len(node_text) > self.max_chars:
                    node_text = self._class_context_text(
                        node,
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
            yield from self._walk_tree_sitter_declarations(
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

    def _safe_code_chunks(self, document: RawDocument) -> list[KnowledgeChunk]:
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
                    kind=ChunkKind.CODE_SYMBOL,
                    text=text_range.text,
                    start_line=text_range.start_line,
                    end_line=text_range.end_line,
                    part=text_range.part,
                )
            )
        return chunks

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
