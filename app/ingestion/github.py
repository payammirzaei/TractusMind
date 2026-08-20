from fnmatch import fnmatchcase
from pathlib import PurePosixPath

from app.ingestion.github_client import GitHubApiClient, GitHubSourceError
from app.ingestion.models import SourceDefinition, SourceFile, SourceManifest


def _pattern_matches(path: str, pattern: str) -> bool:
    patterns = {pattern}
    if pattern.startswith("**/"):
        patterns.add(pattern[3:])
    if "/**/" in pattern:
        patterns.add(pattern.replace("/**/", "/"))
    return any(fnmatchcase(path, candidate) for candidate in patterns)


def _is_selected(path: str, source: SourceDefinition) -> bool:
    included = not source.include or any(
        _pattern_matches(path, pattern) for pattern in source.include
    )
    excluded = any(_pattern_matches(path, pattern) for pattern in source.exclude)
    return included and not excluded


def _content_type(path: str) -> str:
    filename = PurePosixPath(path).name.lower()
    suffix = PurePosixPath(path).suffix.lower()

    if filename.startswith("readme") or suffix == ".md":
        return "documentation"
    if suffix in {".py", ".java", ".kt", ".kts", ".ts", ".tsx", ".js"}:
        return "code"
    if suffix == ".ttl":
        return "semantic_model"
    if suffix in {".json", ".jsonld"}:
        return "structured_data"
    if suffix in {".yaml", ".yml", ".properties", ".toml"}:
        return "configuration"
    return "text"


class GitHubSourceScanner:
    def __init__(
        self,
        token: str | None = None,
        timeout: float = 30.0,
        client: GitHubApiClient | None = None,
    ) -> None:
        self._owns_client = client is None
        self._client = client or GitHubApiClient(token=token, timeout=timeout)

    async def close(self) -> None:
        if self._owns_client:
            await self._client.close()

    async def __aenter__(self) -> "GitHubSourceScanner":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def discover(self, source: SourceDefinition) -> SourceManifest:
        repository = await self._client.get_json(f"/repos/{source.full_name}")
        archived = bool(repository.get("archived", False))
        if archived and not source.allow_archived:
            raise GitHubSourceError(f"Refusing archived source: {source.full_name}")

        commit = await self._client.get_json(f"/repos/{source.full_name}/commits/{source.ref}")
        commit_sha = str(commit["sha"])
        tree_sha = str(commit["commit"]["tree"]["sha"])

        tree = await self._client.get_json(
            f"/repos/{source.full_name}/git/trees/{tree_sha}",
            params={"recursive": "1"},
        )
        tree_truncated = bool(tree.get("truncated", False))

        files: list[SourceFile] = []
        for item in tree.get("tree", []):
            if item.get("type") != "blob":
                continue

            path = str(item["path"])
            size = int(item.get("size") or 0)
            if size > source.max_file_bytes or not _is_selected(path, source):
                continue

            files.append(
                SourceFile(
                    path=path,
                    sha=str(item["sha"]),
                    size=size,
                    content_type=_content_type(path),
                )
            )

        files.sort(key=lambda file: file.path)
        return SourceManifest(
            source_id=source.id,
            repository=source.full_name,
            component=source.component,
            requested_ref=source.ref,
            commit_sha=commit_sha,
            archived=archived,
            files=files,
            tree_truncated=tree_truncated,
        )


__all__ = ["GitHubSourceError", "GitHubSourceScanner"]
