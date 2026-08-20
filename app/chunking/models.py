import hashlib
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from app.ingestion.models import RawDocument


class ChunkKind(StrEnum):
    DOCUMENT_SECTION = "document_section"
    CODE_SYMBOL = "code_symbol"
    STRUCTURED_OBJECT = "structured_object"
    SEMANTIC_ENTITY = "semantic_entity"
    TEXT = "text"


class KnowledgeChunk(BaseModel):
    """A traceable retrieval unit derived from one immutable source document."""

    chunk_id: str
    document_id: str
    source_id: str
    repository: str
    component: str
    commit_sha: str
    path: str
    blob_sha: str
    content_type: str
    language: str | None = None
    kind: ChunkKind
    text: str = Field(min_length=1)
    text_sha256: str
    source_url: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    symbol: str | None = None
    parent_symbol: str | None = None
    section_path: list[str] = Field(default_factory=list)
    part: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_line_range(self) -> "KnowledgeChunk":
        if self.end_line < self.start_line:
            raise ValueError("end_line must be greater than or equal to start_line")
        return self

    @property
    def line_source_url(self) -> str:
        if self.start_line == self.end_line:
            return f"{self.source_url}#L{self.start_line}"
        return f"{self.source_url}#L{self.start_line}-L{self.end_line}"


def make_chunk(
    document: RawDocument,
    *,
    kind: ChunkKind,
    text: str,
    start_line: int,
    end_line: int,
    symbol: str | None = None,
    parent_symbol: str | None = None,
    section_path: list[str] | None = None,
    part: int = 1,
) -> KnowledgeChunk:
    normalized_text = text.strip()
    text_sha256 = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
    identity = ":".join(
        [
            document.document_id,
            kind.value,
            str(start_line),
            str(end_line),
            symbol or "",
            str(part),
            text_sha256,
        ]
    )
    chunk_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()

    return KnowledgeChunk(
        chunk_id=chunk_id,
        document_id=document.document_id,
        source_id=document.source_id,
        repository=document.repository,
        component=document.component,
        commit_sha=document.commit_sha,
        path=document.path,
        blob_sha=document.blob_sha,
        content_type=document.content_type,
        language=document.language,
        kind=kind,
        text=normalized_text,
        text_sha256=text_sha256,
        source_url=document.source_url,
        start_line=start_line,
        end_line=end_line,
        symbol=symbol,
        parent_symbol=parent_symbol,
        section_path=section_path or [],
        part=part,
    )
