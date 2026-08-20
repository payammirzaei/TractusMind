import asyncio
import base64
import hashlib
from collections.abc import Sequence
from pathlib import PurePosixPath
from urllib.parse import quote

from app.ingestion.github_client import GitHubApiClient, GitHubSourceError
from app.ingestion.models import RawDocument, SourceFile, SourceManifest

_LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".json": "json",
    ".jsonld": "jsonld",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".ttl": "turtle",
    ".md": "markdown",
    ".properties": "properties",
    ".toml": "toml",
}


def language_for_path(path: str) -> str | None:
    return _LANGUAGE_BY_SUFFIX.get(PurePosixPath(path).suffix.lower())


def _document_id(repository: str, commit_sha: str, path: str) -> str:
    identity = f"github:{repository}:{commit_sha}:{path}".encode()
    return hashlib.sha256(identity).hexdigest()


class GitHubContentFetcher:
    def __init__(
        self,
        token: str | None = None,
        timeout: float = 30.0,
        concurrency: int = 8,
        client: GitHubApiClient | None = None,
    ) -> None:
        self._owns_client = client is None
        self._client = client or GitHubApiClient(token=token, timeout=timeout)
        self._semaphore = asyncio.Semaphore(max(1, concurrency))

    async def close(self) -> None:
        if self._owns_client:
            await self._client.close()

    async def __aenter__(self) -> "GitHubContentFetcher":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def fetch_document(
        self,
        manifest: SourceManifest,
        source_file: SourceFile,
    ) -> RawDocument:
        async with self._semaphore:
            payload = await self._client.get_json(
                f"/repos/{manifest.repository}/git/blobs/{source_file.sha}"
            )

        if payload.get("encoding") != "base64":
            raise GitHubSourceError(
                f"Unsupported GitHub blob encoding for {manifest.repository}:{source_file.path}"
            )

        try:
            raw_bytes = base64.b64decode(str(payload["content"]), validate=False)
            content = raw_bytes.decode("utf-8")
        except (KeyError, ValueError, UnicodeDecodeError) as exc:
            raise GitHubSourceError(
                f"Could not decode UTF-8 source: {manifest.repository}:{source_file.path}"
            ) from exc

        content_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        source_url = (
            f"https://github.com/{manifest.repository}/blob/{manifest.commit_sha}/"
            f"{quote(source_file.path, safe='/')}"
        )

        return RawDocument(
            document_id=_document_id(
                manifest.repository,
                manifest.commit_sha,
                source_file.path,
            ),
            source_id=manifest.source_id,
            repository=manifest.repository,
            component=manifest.component,
            version_ref=manifest.requested_ref,
            commit_sha=manifest.commit_sha,
            path=source_file.path,
            blob_sha=source_file.sha,
            content_type=source_file.content_type,
            language=language_for_path(source_file.path),
            content=content.replace("\r\n", "\n").replace("\r", "\n"),
            content_sha256=content_sha256,
            source_url=source_url,
            size_bytes=len(raw_bytes),
        )

    async def fetch_selected(
        self,
        manifest: SourceManifest,
        files: Sequence[SourceFile],
    ) -> list[RawDocument]:
        return await asyncio.gather(
            *(self.fetch_document(manifest, source_file) for source_file in files)
        )

    async def fetch_documents(
        self,
        manifest: SourceManifest,
        *,
        limit: int | None = None,
    ) -> list[RawDocument]:
        files = manifest.files if limit is None else manifest.files[: max(0, limit)]
        return await self.fetch_selected(manifest, files)
