import hashlib
import hmac
from collections.abc import Sequence

from app.ingestion.models import SourceDefinition


def verify_github_signature(*, body: bytes, signature: str | None, secret: str) -> bool:
    """Verify GitHub's X-Hub-Signature-256 value without timing leaks."""

    if not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def normalize_github_repository(value: str) -> str:
    return value.strip().removesuffix(".git").casefold()


def ref_matches_source(push_ref: str, source_ref: str) -> bool:
    return push_ref in {f"refs/heads/{source_ref}", f"refs/tags/{source_ref}"}


def matching_push_sources(
    *,
    repository_full_name: str,
    push_ref: str,
    sources: Sequence[SourceDefinition],
) -> list[SourceDefinition]:
    repository = normalize_github_repository(repository_full_name)
    return [
        source
        for source in sources
        if source.enabled
        and source.provider.casefold() == "github"
        and normalize_github_repository(source.full_name) == repository
        and ref_matches_source(push_ref, source.ref)
    ]
