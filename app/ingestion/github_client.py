import httpx

GITHUB_API_URL = "https://api.github.com"


class GitHubSourceError(RuntimeError):
    pass


class GitHubApiClient:
    def __init__(self, token: str | None = None, timeout: float = 30.0) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "TractusMind",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.AsyncClient(
            base_url=GITHUB_API_URL,
            headers=headers,
            timeout=timeout,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "GitHubApiClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def get_json(
        self,
        path: str,
        params: dict[str, str] | None = None,
    ) -> dict:
        response = await self._client.get(path, params=params)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise GitHubSourceError(
                f"GitHub request failed ({response.status_code}) for {path}"
            ) from exc

        payload = response.json()
        if not isinstance(payload, dict):
            raise GitHubSourceError(f"Unexpected GitHub response for {path}")
        return payload
