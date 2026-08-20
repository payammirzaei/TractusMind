from enum import StrEnum

from pydantic import BaseModel, Field


class QueryIntent(StrEnum):
    GENERAL = "general"
    SDK = "sdk"
    EDC = "edc"
    DTR = "dtr"
    SEMANTIC = "semantic"
    RELEASE = "release"
    DEBUG = "debug"


class QueryRoute(BaseModel):
    """Deterministic, inspectable routing decision for one user query."""

    intent: QueryIntent = QueryIntent.GENERAL
    source_ids: list[str] = Field(default_factory=list)
    version: str | None = None
    ref: str | None = None
    commit_sha: str | None = None
    reasons: list[str] = Field(default_factory=list)

    @property
    def has_filter(self) -> bool:
        return bool(self.source_ids or self.ref or self.commit_sha)
