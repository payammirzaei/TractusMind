from pydantic import BaseModel, Field


class RetrievalHit(BaseModel):
    chunk_id: str
    score: float
    retrieval_score: float | None = None
    rerank_score: float | None = None
    debug_score: float | None = None
    retrieval_methods: list[str] = Field(default_factory=list)
    text: str
    source_id: str
    repository: str
    component: str
    version_ref: str | None = None
    commit_sha: str
    path: str
    content_type: str
    language: str | None = None
    kind: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    symbol: str | None = None
    parent_symbol: str | None = None
    section_path: list[str] = Field(default_factory=list)
    source_url: str
