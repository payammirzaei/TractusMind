import base64

import pytest

from app.ingestion.content import GitHubContentFetcher, language_for_path
from app.ingestion.github_client import GitHubSourceError
from app.ingestion.models import SourceFile, SourceManifest


class FakeGitHubClient:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.requested_paths: list[str] = []

    async def get_json(self, path: str, params: dict[str, str] | None = None) -> dict:
        self.requested_paths.append(path)
        return {
            "encoding": "base64",
            "content": base64.b64encode(self.content).decode(),
        }


def _manifest() -> SourceManifest:
    return SourceManifest(
        source_id="tractusx-sdk",
        repository="eclipse-tractusx/tractusx-sdk",
        component="sdk",
        requested_ref="v0.9.0",
        commit_sha="abc123",
        archived=False,
        files=[],
    )


@pytest.mark.asyncio
async def test_fetch_document_is_pinned_and_traceable() -> None:
    manifest = _manifest()
    source_file = SourceFile(
        path="examples/demo.py",
        sha="blob456",
        size=20,
        content_type="code",
    )
    fake_client = FakeGitHubClient(b"print('hello')\r\n")
    fetcher = GitHubContentFetcher(client=fake_client)

    document = await fetcher.fetch_document(manifest, source_file)

    assert document.repository == "eclipse-tractusx/tractusx-sdk"
    assert document.version_ref == "v0.9.0"
    assert document.commit_sha == "abc123"
    assert document.blob_sha == "blob456"
    assert document.language == "python"
    assert document.content == "print('hello')\n"
    assert document.source_url.endswith("/blob/abc123/examples/demo.py")
    assert len(document.content_sha256) == 64
    assert len(document.document_id) == 64
    assert fake_client.requested_paths == [
        "/repos/eclipse-tractusx/tractusx-sdk/git/blobs/blob456"
    ]


@pytest.mark.asyncio
async def test_fetch_document_accepts_cp1252_legacy_text() -> None:
    manifest = _manifest().model_copy(
        update={
            "source_id": "semantic-models",
            "repository": "eclipse-tractusx/sldt-semantic-models",
            "component": "semantic-models",
        }
    )
    source_file = SourceFile(
        path="io.catenax.mandatory_dismantling/1.0.0/MandatoryDismantling.ttl",
        sha="legacy-blob",
        size=64,
        content_type="structured",
    )
    raw = '@prefix ex: <urn:example:> .\r\nex:item ex:label "Größe"@de .\r\n'.encode("cp1252")
    fetcher = GitHubContentFetcher(client=FakeGitHubClient(raw))

    document = await fetcher.fetch_document(manifest, source_file)

    assert document.language == "turtle"
    assert '"Größe"@de' in document.content
    assert "\r" not in document.content
    assert document.content_sha256


@pytest.mark.asyncio
async def test_fetch_document_rejects_binary_looking_legacy_blob() -> None:
    source_file = SourceFile(
        path="model.ttl",
        sha="binary-blob",
        size=4,
        content_type="structured",
    )
    fetcher = GitHubContentFetcher(client=FakeGitHubClient(b"\xff\x00\xfe\x01"))

    with pytest.raises(GitHubSourceError, match="Could not decode text source"):
        await fetcher.fetch_document(_manifest(), source_file)


def test_language_detection() -> None:
    assert language_for_path("src/Main.java") == "java"
    assert language_for_path("model.ttl") == "turtle"
    assert language_for_path("docs/guide.md") == "markdown"
    assert language_for_path("LICENSE") is None
