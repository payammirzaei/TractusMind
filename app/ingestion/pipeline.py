from app.ingestion.content import GitHubContentFetcher
from app.ingestion.github import GitHubSourceScanner
from app.ingestion.github_client import GitHubApiClient, GitHubSourceError
from app.ingestion.models import RawDocument, SourceDefinition, SourceManifest


class SourceIngestionPipeline:
    def __init__(
        self,
        token: str | None = None,
        timeout: float = 30.0,
        concurrency: int = 8,
    ) -> None:
        self._client = GitHubApiClient(token=token, timeout=timeout)
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

    async def fetch(
        self,
        source: SourceDefinition,
        *,
        limit: int | None = None,
    ) -> tuple[SourceManifest, list[RawDocument]]:
        manifest = await self.discover(source)
        documents = await self._fetcher.fetch_documents(manifest, limit=limit)
        return manifest, documents
