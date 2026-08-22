import hashlib
import hmac

from app.ingestion.models import SourceDefinition, SourcePriority
from app.ingestion.webhook import matching_push_sources, verify_github_signature


def source(*, owner: str = "eclipse-tractusx", repo: str = "tractusx-sdk", ref: str = "main") -> SourceDefinition:
    return SourceDefinition(
        id=f"{owner}-{repo}-{ref}",
        owner=owner,
        repo=repo,
        component="test",
        priority=SourcePriority.HIGH,
        ref=ref,
    )


def test_verify_github_signature_accepts_valid_sha256_signature() -> None:
    body = b'{"ref":"refs/heads/main"}'
    secret = "a-long-webhook-secret"
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert verify_github_signature(body=body, signature=signature, secret=secret)


def test_verify_github_signature_rejects_missing_or_tampered_signature() -> None:
    body = b"payload"
    secret = "a-long-webhook-secret"

    assert not verify_github_signature(body=body, signature=None, secret=secret)
    assert not verify_github_signature(body=body, signature="sha256=deadbeef", secret=secret)


def test_matching_push_sources_routes_only_matching_repository_and_ref() -> None:
    expected = source()
    sources = [
        expected,
        source(repo="tractusx-edc"),
        source(ref="release"),
        source(owner="other-org"),
    ]

    matches = matching_push_sources(
        repository_full_name="ECLIPSE-TRACTUSX/TRACTUSX-SDK",
        push_ref="refs/heads/main",
        sources=sources,
    )

    assert matches == [expected]


def test_matching_push_sources_supports_tag_refs() -> None:
    tagged = source(ref="v1.2.3")

    matches = matching_push_sources(
        repository_full_name="eclipse-tractusx/tractusx-sdk",
        push_ref="refs/tags/v1.2.3",
        sources=[tagged],
    )

    assert matches == [tagged]


def test_matching_push_sources_ignores_disabled_sources() -> None:
    disabled = source()
    disabled.enabled = False

    matches = matching_push_sources(
        repository_full_name="eclipse-tractusx/tractusx-sdk",
        push_ref="refs/heads/main",
        sources=[disabled],
    )

    assert matches == []
