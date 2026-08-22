from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class SourcePriority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SourceDefinition(BaseModel):
    id: str
    provider: str = "github"
    owner: str
    repo: str
    component: str
    domain: str = "general"
    source_type: str = "repository"
    catalog_state: Literal["active", "archived", "meta", "empty"] = "active"
    priority: SourcePriority
    ref: str = "main"
    enabled: bool = True
    allow_archived: bool = False
    max_file_bytes: int = Field(default=1_000_000, gt=0)
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"


class SourceFile(BaseModel):
    path: str
    sha: str
    size: int = 0
    content_type: str


class SourceManifest(BaseModel):
    source_id: str
    repository: str
    component: str
    requested_ref: str
    commit_sha: str
    archived: bool
    files: list[SourceFile]
    tree_truncated: bool = False


class RawDocument(BaseModel):
    """Canonical, immutable source document fetched from a pinned repository commit."""

    document_id: str
    source_id: str
    repository: str
    component: str
    version_ref: str = "main"
    commit_sha: str
    path: str
    blob_sha: str
    content_type: str
    language: str | None = None
    content: str
    content_sha256: str
    source_url: str
    size_bytes: int = Field(ge=0)
