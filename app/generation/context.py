from dataclasses import dataclass

from app.generation.models import AnswerCitation
from app.retrieval.models import RetrievalHit


@dataclass(frozen=True)
class EvidenceBlock:
    citation_id: str
    hit: RetrievalHit
    rendered: str


@dataclass(frozen=True)
class GroundedContext:
    blocks: tuple[EvidenceBlock, ...]
    text: str

    @property
    def citations(self) -> dict[str, AnswerCitation]:
        return {
            block.citation_id: AnswerCitation(
                citation_id=block.citation_id,
                chunk_id=block.hit.chunk_id,
                source_id=block.hit.source_id,
                repository=block.hit.repository,
                component=block.hit.component,
                commit_sha=block.hit.commit_sha,
                path=block.hit.path,
                start_line=block.hit.start_line,
                end_line=block.hit.end_line,
                source_url=block.hit.source_url,
                retrieval_score=block.hit.retrieval_score,
                rerank_score=block.hit.rerank_score,
            )
            for block in self.blocks
        }


def _render_block(citation_id: str, hit: RetrievalHit) -> str:
    metadata = [
        f"[{citation_id}]",
        f"source_id: {hit.source_id}",
        f"repository: {hit.repository}",
        f"component: {hit.component}",
        f"commit: {hit.commit_sha}",
        f"path: {hit.path}",
        f"lines: {hit.start_line}-{hit.end_line}",
    ]
    if hit.symbol:
        metadata.append(f"symbol: {hit.symbol}")
    if hit.parent_symbol:
        metadata.append(f"parent_symbol: {hit.parent_symbol}")
    if hit.section_path:
        metadata.append(f"section: {' > '.join(hit.section_path)}")
    return "\n".join(metadata) + "\n---\n" + hit.text.strip()


def build_grounded_context(
    hits: list[RetrievalHit],
    *,
    max_chars: int = 24_000,
) -> GroundedContext:
    if max_chars < 1:
        raise ValueError("max_chars must be greater than zero")

    blocks: list[EvidenceBlock] = []
    used = 0
    for index, hit in enumerate(hits, start=1):
        citation_id = f"S{index}"
        rendered = _render_block(citation_id, hit)
        separator_cost = 2 if blocks else 0
        remaining = max_chars - used - separator_cost
        if remaining <= 0:
            break
        if len(rendered) > remaining:
            if blocks:
                break
            rendered = rendered[:remaining].rstrip()
        blocks.append(EvidenceBlock(citation_id, hit, rendered))
        used += len(rendered) + separator_cost

    return GroundedContext(
        blocks=tuple(blocks),
        text="\n\n".join(block.rendered for block in blocks),
    )
