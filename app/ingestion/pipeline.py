from collections.abc import Sequence

from app.ingestion.content import GitHubContentFetcher
from app.ingestion.github import GitHubSourceScanner
from app.ingestion.github_client import GitHubApiClient, GitHubSourceError
from app.ingestion.models import RawDocument, SourceDefinition, SourceFile, SourceManifest


class SourceIngestionPipeline:
    def __init__(
        self,
        token: str | None = None,
        timeout: float = 30.0,
        concurrency: int = 8,
        *,
        max_attempts: int = 4,
        retry_base_seconds: float = 0.5,
        retry_max_seconds: float = 8.0,
        circuit_failure_threshold: int = 3,
        circuit_cooldown_seconds: float = 30.0,
    ) -> None:
        self._client = GitHubApiClient(
            token=token,
            timeout=timeout,
            max_attempts=max_attempts,
            retry_base_seconds=retry_base_seconds,
            retry_max_seconds=retry_max_seconds,
            circuit_failure_threshold=circuit_failure_threshold,
            circuit_cooldown_seconds=circuit_cooldown_seconds,
        )
        self._scanner = GitHubSourceScanner(client=self._client)
        self._fetcher = GitHubContentFetcher(
            client=self._client,
            concurrency=concurrency,
        )

    async def close(self) -> None:
        await self._client.close()

    async def __aenter__(self) -> "SourceIngestionPipeline":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def discover(self, source: SourceDefinition) -> SourceManifest:
        manifest = await self._scanner.discover(source)
        if manifest.tree_truncated:
            raise GitHubSourceError(
                "GitHub returned a truncated repository tree for "
                f"{manifest.repository}; refusing incomplete ingestion"
            )
        return manifest

    async def fetch_files(
        self,
        manifest: SourceManifest,
        files: Sequence[SourceFile],
    ) -> list[RawDocument]:
        return await self._fetcher.fetch_selected(manifest, files)

    async def fetch(
        self,
        source: SourceDefinition,
        *,
        limit: int | None = None,
    ) -> tuple[SourceManifest, list[RawDocument]]:
        manifest = await self.discover(source)
        documents = await self._fetcher.fetch_documents(manifest, limit=limit)
        return manifest, documents
