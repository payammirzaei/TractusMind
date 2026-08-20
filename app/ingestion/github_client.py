import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from time import time

import httpx

from app.observability.metrics import (
    PROVIDER_CIRCUIT_OPEN,
    PROVIDER_REQUESTS,
    PROVIDER_RETRIES,
    PROVIDER_RETRY_DELAY,
)
from app.resilience import (
    CircuitOpenError,
    parse_retry_after,
    shared_provider_circuit,
    sleep_before_retry,
)

GITHUB_API_URL = "https://api.github.com"
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class GitHubSourceError(RuntimeError):
    pass


class GitHubApiClient:
    def __init__(
        self,
        token: str | None = None,
        timeout: float = 30.0,
        *,
        max_attempts: int = 4,
        retry_base_seconds: float = 0.5,
        retry_max_seconds: float = 8.0,
        circuit_failure_threshold: int = 3,
        circuit_cooldown_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("GitHub max_attempts must be positive")
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "TractusMind",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.max_attempts = max_attempts
        self.retry_base_seconds = retry_base_seconds
        self.retry_max_seconds = retry_max_seconds
        self._sleep = sleep
        credential_scope = hashlib.sha256(
            (token or "anonymous").encode("utf-8")
        ).hexdigest()[:16]
        self._breaker = shared_provider_circuit(
            provider="github",
            scope=credential_scope,
            failure_threshold=circuit_failure_threshold,
            cooldown_seconds=circuit_cooldown_seconds,
        )
        self._client = httpx.AsyncClient(
            base_url=GITHUB_API_URL,
            headers=headers,
            timeout=timeout,
            transport=transport,
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
        operation = "get_json"
        try:
            await self._breaker.before_call()
        except CircuitOpenError as exc:
            PROVIDER_CIRCUIT_OPEN.labels(provider="github", event="rejected").inc()
            PROVIDER_REQUESTS.labels(
                provider="github", operation=operation, outcome="circuit_open"
            ).inc()
            raise GitHubSourceError("GitHub provider circuit is open") from exc

        transient_error: Exception | None = None
        transient_reason = "unknown"
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = await self._client.get(path, params=params)
            except httpx.TransportError as exc:
                transient_error = exc
                transient_reason = (
                    "timeout"
                    if isinstance(exc, httpx.TimeoutException)
                    else "transport"
                )
                if attempt < self.max_attempts:
                    await self._retry(
                        attempt=attempt,
                        operation=operation,
                        reason=transient_reason,
                        retry_after=None,
                    )
                    continue
                break

            retryable = response.status_code in _RETRYABLE_STATUS_CODES
            if response.status_code == 403 and self._is_rate_limited(response):
                retryable = True
            if retryable:
                transient_error = GitHubSourceError(
                    f"GitHub request failed ({response.status_code}) for {path}"
                )
                transient_reason = (
                    "rate_limit"
                    if response.status_code in {403, 429}
                    else f"http_{response.status_code}"
                )
                if attempt < self.max_attempts:
                    await self._retry(
                        attempt=attempt,
                        operation=operation,
                        reason=transient_reason,
                        retry_after=self._retry_after(response),
                    )
                    continue
                break

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                await self._breaker.record_success()
                PROVIDER_REQUESTS.labels(
                    provider="github", operation=operation, outcome="http_error"
                ).inc()
                raise GitHubSourceError(
                    f"GitHub request failed ({response.status_code}) for {path}"
                ) from exc

            await self._breaker.record_success()
            try:
                payload = response.json()
            except ValueError as exc:
                PROVIDER_REQUESTS.labels(
                    provider="github", operation=operation, outcome="invalid_response"
                ).inc()
                raise GitHubSourceError(f"Unexpected GitHub response for {path}") from exc
            if not isinstance(payload, dict):
                PROVIDER_REQUESTS.labels(
                    provider="github", operation=operation, outcome="invalid_response"
                ).inc()
                raise GitHubSourceError(f"Unexpected GitHub response for {path}")

            PROVIDER_REQUESTS.labels(
                provider="github", operation=operation, outcome="success"
            ).inc()
            return payload

        opened = await self._breaker.record_transient_failure()
        if opened:
            PROVIDER_CIRCUIT_OPEN.labels(provider="github", event="opened").inc()
        PROVIDER_REQUESTS.labels(
            provider="github", operation=operation, outcome="transient_failure"
        ).inc()
        if transient_error is None:
            transient_error = RuntimeError(transient_reason)
        raise GitHubSourceError(
            f"GitHub request failed after {self.max_attempts} attempts "
            f"({transient_reason}) for {path}"
        ) from transient_error

    async def _retry(
        self,
        *,
        attempt: int,
        operation: str,
        reason: str,
        retry_after: float | None,
    ) -> None:
        PROVIDER_RETRIES.labels(
            provider="github", operation=operation, reason=reason
        ).inc()
        delay = await sleep_before_retry(
            attempt,
            base_seconds=self.retry_base_seconds,
            max_seconds=self.retry_max_seconds,
            retry_after=retry_after,
            sleep=self._sleep,
        )
        PROVIDER_RETRY_DELAY.labels(provider="github", operation=operation).observe(delay)

    @staticmethod
    def _is_rate_limited(response: httpx.Response) -> bool:
        if response.headers.get("Retry-After"):
            return True
        if response.headers.get("X-RateLimit-Remaining") == "0":
            return True
        try:
            payload = response.json()
        except ValueError:
            return False
        message = ""
        if isinstance(payload, dict):
            message = str(payload.get("message", "")).casefold()
        return "rate limit" in message

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        retry_after = parse_retry_after(response.headers.get("Retry-After"))
        if retry_after is not None:
            return retry_after
        reset = response.headers.get("X-RateLimit-Reset")
        if not reset:
            return None
        try:
            return max(0.0, float(reset) - time())
        except ValueError:
            return None
