import asyncio
import re
from dataclasses import dataclass

from qdrant_client import models

from app.retrieval.hybrid import HybridRetrievalService
from app.retrieval.models import RetrievalHit
from app.routing.filters import build_route_filter
from app.routing.models import QueryRoute

_QUOTED_RE = re.compile(r'["`]([^"`\n]{3,180})["`]')
_PATH_RE = re.compile(r"(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+")
_EXCEPTION_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_.]*(?:Exception|Error)\b")
_CAMEL_RE = re.compile(r"\b[A-Z][a-zA-Z0-9]*(?:[A-Z][a-zA-Z0-9]*)+\b")
_SNAKE_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+\b")
_DOTTED_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)+\b")
_ENV_RE = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")
_HTTP_RE = re.compile(r"\b(?:4\d\d|5\d\d)\b")
_ERROR_LINE_RE = re.compile(
    r"error|exception|traceback|failed|failure|cannot|could not|unknown|not found",
    re.I,
)


@dataclass(frozen=True)
class DebugQueryTerms:
    phrases: tuple[str, ...]
    identifiers: tuple[str, ...]
    paths: tuple[str, ...]
    codes: tuple[str, ...]

    @property
    def empty(self) -> bool:
        return not (self.phrases or self.identifiers or self.paths or self.codes)


def extract_debug_terms(query: str) -> DebugQueryTerms:
    phrases: list[str] = []
    identifiers: list[str] = []
    paths: list[str] = []
    codes: list[str] = []

    for match in _QUOTED_RE.finditer(query):
        _append_unique(phrases, match.group(1).strip(), limit=6)

    for raw_line in query.splitlines():
        line = raw_line.strip()
        if 6 <= len(line) <= 180 and _ERROR_LINE_RE.search(line):
            _append_unique(phrases, line, limit=6)

    for pattern in (
        _EXCEPTION_RE,
        _CAMEL_RE,
        _SNAKE_RE,
        _DOTTED_RE,
        _ENV_RE,
    ):
        for match in pattern.finditer(query):
            _append_unique(identifiers, match.group(0), limit=12)

    for match in _PATH_RE.finditer(query):
        value = match.group(0)
        _append_unique(paths, value, limit=6)
        _append_unique(identifiers, value.rsplit("/", 1)[-1], limit=12)

    for match in _HTTP_RE.finditer(query):
        _append_unique(codes, match.group(0), limit=4)

    return DebugQueryTerms(
        phrases=tuple(phrases),
        identifiers=tuple(identifiers),
        paths=tuple(paths),
        codes=tuple(codes),
    )


class DebugRetrievalService:
    """Fuse exact debugging evidence with the normal hybrid retrieval lane."""

    def __init__(
        self,
        retrieval: HybridRetrievalService,
        *,
        exact_k: int = 30,
        rrf_k: int = 60,
        exact_weight: float = 1.5,
        hybrid_weight: float = 1.0,
    ) -> None:
        if exact_k < 1 or rrf_k < 1:
            raise ValueError("exact_k and rrf_k must be greater than zero")
        self.retrieval = retrieval
        self.exact_k = exact_k
        self.rrf_k = rrf_k
        self.exact_weight = exact_weight
        self.hybrid_weight = hybrid_weight

    async def search_candidates(
        self,
        query: str,
        *,
        route: QueryRoute,
        limit: int,
        prefetch_limit: int,
    ) -> list[RetrievalHit]:
        terms = extract_debug_terms(query)
        conditions = self._conditions(terms)
        if not conditions:
            return await self.retrieval.search_hybrid(
                query,
                limit=limit,
                prefetch_limit=prefetch_limit,
                route=route,
            )

        query_filter = build_route_filter(route)
        hybrid_task = self.retrieval.search_hybrid(
            query,
            limit=limit,
            prefetch_limit=prefetch_limit,
            route=route,
        )
        exact_task = self.retrieval.store.debug_search(
            conditions,
            query_filter=query_filter,
            limit=self.exact_k,
        )
        hybrid, exact = await asyncio.gather(hybrid_task, exact_task)
        return self._fuse(exact, hybrid, limit=limit)

    def _conditions(
        self,
        terms: DebugQueryTerms,
    ) -> list[tuple[models.FieldCondition, float, str]]:
        conditions: list[tuple[models.FieldCondition, float, str]] = []

        for phrase in terms.phrases:
            conditions.append(
                (
                    models.FieldCondition(
                        key="debug_text",
                        match=models.MatchPhrase(phrase=phrase),
                    ),
                    3.0,
                    "exact_phrase",
                )
            )

        for path in terms.paths:
            conditions.append(
                (
                    models.FieldCondition(
                        key="path",
                        match=models.MatchValue(value=path),
                    ),
                    4.0,
                    "exact_path",
                )
            )

        for identifier in terms.identifiers:
            conditions.extend(
                [
                    (
                        models.FieldCondition(
                            key="symbol",
                            match=models.MatchValue(value=identifier),
                        ),
                        4.0,
                        "exact_symbol",
                    ),
                    (
                        models.FieldCondition(
                            key="parent_symbol",
                            match=models.MatchValue(value=identifier),
                        ),
                        3.5,
                        "exact_parent_symbol",
                    ),
                    (
                        models.FieldCondition(
                            key="debug_text",
                            match=models.MatchText(text=identifier),
                        ),
                        2.0,
                        "identifier_text",
                    ),
                ]
            )

        for code in terms.codes:
            conditions.append(
                (
                    models.FieldCondition(
                        key="debug_text",
                        match=models.MatchText(text=code),
                    ),
                    1.5,
                    "error_code",
                )
            )

        return conditions

    def _fuse(
        self,
        exact: list[RetrievalHit],
        hybrid: list[RetrievalHit],
        *,
        limit: int,
    ) -> list[RetrievalHit]:
        merged: dict[str, RetrievalHit] = {}
        scores: dict[str, float] = {}
        methods: dict[str, set[str]] = {}

        for weight, hits in (
            (self.exact_weight, exact),
            (self.hybrid_weight, hybrid),
        ):
            for rank, hit in enumerate(hits, start=1):
                chunk_id = hit.chunk_id
                scores[chunk_id] = scores.get(chunk_id, 0.0) + weight / (
                    self.rrf_k + rank
                )
                methods.setdefault(chunk_id, set()).update(hit.retrieval_methods)
                current = merged.get(chunk_id)
                if current is None or (
                    hit.debug_score is not None
                    and current.debug_score is None
                ):
                    merged[chunk_id] = hit
                elif hit.debug_score is not None:
                    merged[chunk_id] = current.model_copy(
                        update={"debug_score": hit.debug_score}
                    )

        fused = [
            hit.model_copy(
                update={
                    "score": scores[chunk_id],
                    "retrieval_methods": sorted(methods[chunk_id]),
                }
            )
            for chunk_id, hit in merged.items()
        ]
        fused.sort(key=lambda hit: (hit.score, hit.chunk_id), reverse=True)
        return fused[:limit]


def _append_unique(values: list[str], value: str, *, limit: int) -> None:
    normalized = value.strip()
    if normalized and normalized not in values and len(values) < limit:
        values.append(normalized)
