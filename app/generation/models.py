from pydantic import BaseModel, Field


class AnswerCitation(BaseModel):
    citation_id: str
    chunk_id: str
    repository: str
    component: str
    commit_sha: str
    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    source_url: str
    retrieval_score: float | None = None
    rerank_score: float | None = None


class GroundedAnswer(BaseModel):
    question: str
    answer: str
    grounded: bool
    abstained: bool
    evidence_count: int = Field(ge=0)
    citations: list[AnswerCitation] = Field(default_factory=list)
    model: str | None = None


class LLMAnswerPayload(BaseModel):
    answer: str = Field(min_length=1)
    citation_ids: list[str] = Field(default_factory=list)
    grounded: bool
