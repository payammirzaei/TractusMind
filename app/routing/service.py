import re

from app.routing.models import QueryIntent, QueryRoute

_SDK_TERMS = (
    "tractus-x sdk",
    "tractusx sdk",
    "tractusx_sdk",
    "python sdk",
    " sdk ",
)
_EDC_TERMS = (
    " edc ",
    "connector",
    "contract definition",
    "policy definition",
    "transfer process",
    "data plane",
    "control plane",
)
_DTR_TERMS = (
    "digital twin registry",
    " dtr ",
    "shell descriptor",
    "aas registry",
    "asset administration shell",
)
_SEMANTIC_TERMS = (
    "samm",
    "semantic model",
    "aspect model",
    "aspect-model",
    "turtle",
    ".ttl",
    "rdf",
)
_DEBUG_TERMS = (
    " error",
    "exception",
    "traceback",
    "stack trace",
    "stacktrace",
    " failed",
    " failure",
    "cannot ",
    "can't ",
    "could not ",
    "unknown ",
    "not found",
)
_RELEASE_TERMS = (
    "release",
    "version",
    "compatibility",
    "changelog",
    "migration",
)

_VERSION_PATTERNS = (
    re.compile(r"\b(?:version|release)\s*[:=]?\s*v?(\d+\.\d+(?:\.\d+)?)\b", re.I),
    re.compile(r"\bv(\d+\.\d+(?:\.\d+)?)\b", re.I),
    re.compile(r"\bR(\d{2}\.\d{2})\b", re.I),
)
_REF_RE = re.compile(r"\bref\s*[:=]\s*([A-Za-z0-9._/-]+)", re.I)
_COMMIT_RE = re.compile(r"\bcommit\s*[:=]\s*([0-9a-f]{7,40})\b", re.I)
_HTTP_ERROR_RE = re.compile(r"\b(?:4\d\d|5\d\d)\b")
_MATCHING_PUNCTUATION_RE = re.compile(r"[^\w./-]+", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")


class QueryRouter:
    """Route Tractus-X queries without adding an LLM call to retrieval."""

    def route(self, query: str) -> QueryRoute:
        if not query.strip():
            raise ValueError("Query must not be empty")

        normalized = self._normalize_for_matching(query)
        sdk = self._contains_any(normalized, _SDK_TERMS)
        edc = self._contains_any(normalized, _EDC_TERMS)
        dtr = self._contains_any(normalized, _DTR_TERMS)
        semantic = self._contains_any(normalized, _SEMANTIC_TERMS)
        debug = self._contains_any(normalized, _DEBUG_TERMS) or bool(
            _HTTP_ERROR_RE.search(normalized)
        )
        version = self._extract_version(query)
        release = self._contains_any(normalized, _RELEASE_TERMS) or version is not None
        ref = self._extract(_REF_RE, query)
        commit_sha = self._extract(_COMMIT_RE, query)

        # Asset creation is a cross-cutting EDC/SDK task unless the user names one side.
        if " asset " in normalized and not (sdk or edc):
            sdk = True
            edc = True

        source_ids: list[str] = []
        reasons: list[str] = []

        if sdk:
            self._extend(source_ids, "tractusx-sdk", "tractusx-docs")
            reasons.append("matched_sdk")
        if edc:
            self._extend(source_ids, "tractusx-edc", "tractusx-docs")
            reasons.append("matched_edc")
        if dtr:
            self._extend(source_ids, "digital-twin-registry", "tractusx-docs")
            reasons.append("matched_dtr")
        if semantic:
            self._extend(source_ids, "semantic-models", "tractusx-docs")
            reasons.append("matched_semantic_models")
        if release:
            self._extend(source_ids, "tractusx-release", "tractusx-docs")
            reasons.append("matched_release_or_version")

        if debug and not source_ids:
            self._extend(
                source_ids,
                "tractusx-sdk",
                "tractusx-edc",
                "digital-twin-registry",
                "tractusx-docs",
            )
            reasons.append("debug_default_code_sources")

        if version is not None:
            reasons.append(f"version:{version}")
        if ref is not None:
            reasons.append(f"ref:{ref}")
        if commit_sha is not None:
            reasons.append(f"commit:{commit_sha}")

        intent = self._intent(
            sdk=sdk,
            edc=edc,
            dtr=dtr,
            semantic=semantic,
            release=release,
            debug=debug,
            normalized=normalized,
        )
        if not reasons:
            reasons.append("no_specific_route_signal")

        return QueryRoute(
            intent=intent,
            source_ids=source_ids,
            version=version,
            ref=ref,
            commit_sha=commit_sha,
            reasons=reasons,
        )

    def _intent(
        self,
        *,
        sdk: bool,
        edc: bool,
        dtr: bool,
        semantic: bool,
        release: bool,
        debug: bool,
        normalized: str,
    ) -> QueryIntent:
        if debug:
            return QueryIntent.DEBUG
        if semantic:
            return QueryIntent.SEMANTIC
        if dtr:
            return QueryIntent.DTR
        if " edc " in normalized or (edc and not sdk):
            return QueryIntent.EDC
        if " sdk " in normalized or "tractusx_sdk" in normalized or (sdk and not edc):
            return QueryIntent.SDK
        if release:
            return QueryIntent.RELEASE
        return QueryIntent.GENERAL

    def _extract_version(self, query: str) -> str | None:
        for pattern in _VERSION_PATTERNS:
            match = pattern.search(query)
            if match:
                return match.group(1)
        return None

    def _extract(self, pattern: re.Pattern[str], query: str) -> str | None:
        match = pattern.search(query)
        return match.group(1) if match else None

    def _normalize_for_matching(self, text: str) -> str:
        normalized = _MATCHING_PUNCTUATION_RE.sub(" ", text.casefold())
        normalized = _WHITESPACE_RE.sub(" ", normalized).strip()
        return f" {normalized} "

    def _contains_any(self, text: str, terms: tuple[str, ...]) -> bool:
        for term in terms:
            needle = self._normalize_for_matching(term).strip()
            if f" {needle} " in text:
                return True
        return False

    def _extend(self, values: list[str], *items: str) -> None:
        for item in items:
            if item not in values:
                values.append(item)
