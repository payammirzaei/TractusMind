import httpx
import pytest

from app.generation.llm import LLMGenerationError, OpenAICompatibleLLM
from app.ingestion.github_client import GitHubApiClient, GitHubSourceError
from app.resilience import CircuitOpenError, ProviderCircuitBreaker, backoff_seconds


async def _no_sleep(_delay: float) -> None:
    return None


async def test_llm_retries_transient_status_with_stable_idempotency_key() -> None:
    attempts = 0
    idempotency_keys: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        idempotency_keys.append(request.headers["Idempotency-Key"])
        if attempts == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(
            200,
            request=request,
            json={"choices": [{"message": {"content": "grounded"}}]},
        )

    llm = OpenAICompatibleLLM(
        base_url="https://llm.example/v1",
        model_name="test-model",
        max_attempts=3,
        retry_base_seconds=0,
        retry_max_seconds=0.1,
        transport=httpx.MockTransport(handler),
        sleep=_no_sleep,
    )
    try:
        result = await llm.complete("system", "user")
    finally:
        await llm.close()

    assert result == "grounded"
    assert attempts == 2
    assert len(set(idempotency_keys)) == 1


async def test_llm_does_not_retry_non_transient_client_error() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(400, request=request)

    llm = OpenAICompatibleLLM(
        base_url="https://llm.example/v1",
        model_name="test-model",
        max_attempts=3,
        transport=httpx.MockTransport(handler),
        sleep=_no_sleep,
    )
    try:
        with pytest.raises(LLMGenerationError, match="status 400"):
            await llm.complete("system", "user")
    finally:
        await llm.close()

    assert attempts == 1


async def test_github_retries_rate_limit_response() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(
                403,
                request=request,
                headers={"Retry-After": "1", "X-RateLimit-Remaining": "0"},
                json={"message": "API rate limit exceeded"},
            )
        return httpx.Response(200, request=request, json={"sha": "abc"})

    client = GitHubApiClient(
        max_attempts=3,
        retry_base_seconds=0,
        retry_max_seconds=0.1,
        transport=httpx.MockTransport(handler),
        sleep=_no_sleep,
    )
    try:
        payload = await client.get_json("/repos/example/project")
    finally:
        await client.close()

    assert payload == {"sha": "abc"}
    assert attempts == 2


async def test_github_does_not_retry_not_found() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(404, request=request, json={"message": "Not Found"})

    client = GitHubApiClient(
        max_attempts=4,
        transport=httpx.MockTransport(handler),
        sleep=_no_sleep,
    )
    try:
        with pytest.raises(GitHubSourceError, match=r"\(404\)"):
            await client.get_json("/repos/example/missing")
    finally:
        await client.close()

    assert attempts == 1


async def test_circuit_breaker_rejects_until_half_open_probe() -> None:
    now = 100.0

    def clock() -> float:
        return now

    breaker = ProviderCircuitBreaker(
        provider="test",
        failure_threshold=2,
        cooldown_seconds=10,
        clock=clock,
    )

    await breaker.before_call()
    assert await breaker.record_transient_failure() is False
    await breaker.before_call()
    assert await breaker.record_transient_failure() is True

    with pytest.raises(CircuitOpenError):
        await breaker.before_call()

    now = 111.0
    await breaker.before_call()
    with pytest.raises(CircuitOpenError):
        await breaker.before_call()

    await breaker.record_success()
    await breaker.before_call()


def test_backoff_respects_provider_retry_after_cap() -> None:
    delay = backoff_seconds(
        1,
        base_seconds=0.5,
        max_seconds=8.0,
        retry_after=60.0,
    )

    assert delay == 8.0
