import base64

import pytest

from app.ingestion.content import GitHubContentFetcher, language_for_path
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


@pytest.mark.asyncio
async def test_fetch_document_is_pinned_and_traceable() -> None:
    manifest = SourceManifest(
        source_id="tractusx-sdk",
        repository="eclipse-tractusx/tractusx-sdk",
        component="sdk",
        requested_ref="main",
        commit_sha="abc123",
        archived=False,
        files=[],
    )
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


def test_language_detection() -> None:
    assert language_for_path("src/Main.java") == "java"
    assert language_for_path("model.ttl") == "turtle"
    assert language_for_path("docs/guide.md") == "markdown"
    assert language_for_path("LICENSE") is None
