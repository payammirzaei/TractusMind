import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Protocol
from uuid import uuid4

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


class LLMConfigurationError(RuntimeError):
    pass


class LLMGenerationError(RuntimeError):
    pass


class LLMProvider(Protocol):
    model_name: str

    async def complete(self, system_prompt: str, user_prompt: str) -> str: ...

    async def close(self) -> None: ...


_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
_JSON_RETRY_INSTRUCTION = (
    "\n\nYour previous response could not be accepted as complete JSON. "
    "Return one compact valid JSON object only, with no markdown or prose outside it. "
    "Keep the response concise enough to finish within the token limit."
)


class OpenAICompatibleLLM:
    def __init__(
        self,
        *,
        base_url: str,
        model_name: str,
        api_key: str | None = None,
        timeout: float = 60.0,
        temperature: float = 0.0,
        max_tokens: int = 1_500,
        max_attempts: int = 3,
        retry_base_seconds: float = 0.5,
        retry_max_seconds: float = 8.0,
        circuit_failure_threshold: int = 3,
        circuit_cooldown_seconds: float = 30.0,
        json_mode: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not base_url.strip():
            raise LLMConfigurationError("LLM_BASE_URL is required")
        if not model_name.strip():
            raise LLMConfigurationError("LLM_MODEL is required")
        if max_attempts < 1:
            raise LLMConfigurationError("LLM max_attempts must be positive")

        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_attempts = max_attempts
        self.retry_base_seconds = retry_base_seconds
        self.retry_max_seconds = retry_max_seconds
        self.json_mode = json_mode
        self._sleep = sleep
        scope_source = f"{base_url.rstrip('/')}|{model_name}".encode()
        self._breaker = shared_provider_circuit(
            provider="llm",
            scope=hashlib.sha256(scope_source).hexdigest()[:16],
            failure_threshold=circuit_failure_threshold,
            cooldown_seconds=circuit_cooldown_seconds,
        )
        headers = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(
            base_url=f"{base_url.rstrip('/')}/",
            headers=headers,
            timeout=timeout,
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        operation = "chat_completions"
        try:
            await self._breaker.before_call()
        except CircuitOpenError as exc:
            PROVIDER_CIRCUIT_OPEN.labels(provider="llm", event="rejected").inc()
            PROVIDER_REQUESTS.labels(
                provider="llm", operation=operation, outcome="circuit_open"
            ).inc()
            raise LLMGenerationError("LLM provider circuit is open") from exc

        idempotency_key = str(uuid4())
        transient_error: Exception | None = None
        transient_reason = "unknown"
        json_retry = False
        for attempt in range(1, self.max_attempts + 1):
            request_system_prompt = system_prompt
            if self.json_mode and json_retry:
                request_system_prompt += _JSON_RETRY_INSTRUCTION

            request_payload: dict[str, object] = {
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": request_system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            }
            if self.json_mode:
                request_payload["response_format"] = {"type": "json_object"}

            try:
                response = await self._client.post(
                    "chat/completions",
                    headers={"Idempotency-Key": idempotency_key},
                    json=request_payload,
                )
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

            if response.status_code in _RETRYABLE_STATUS_CODES:
                transient_error = LLMGenerationError(
                    f"LLM request failed with status {response.status_code}"
                )
                transient_reason = f"http_{response.status_code}"
                if attempt < self.max_attempts:
                    await self._retry(
                        attempt=attempt,
                        operation=operation,
                        reason=transient_reason,
                        retry_after=parse_retry_after(response.headers.get("Retry-After")),
                    )
                    continue
                break

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                await self._breaker.record_success()
                PROVIDER_REQUESTS.labels(
                    provider="llm", operation=operation, outcome="http_error"
                ).inc()
                raise LLMGenerationError(
                    f"LLM request failed with status {response.status_code}"
                ) from exc

            await self._breaker.record_success()
            try:
                payload = response.json()
                choice = payload["choices"][0]
                content = choice["message"]["content"]
                finish_reason = choice.get("finish_reason")
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                PROVIDER_REQUESTS.labels(
                    provider="llm", operation=operation, outcome="invalid_response"
                ).inc()
                raise LLMGenerationError("Unexpected LLM response shape") from exc
            if not isinstance(content, str) or not content.strip():
                PROVIDER_REQUESTS.labels(
                    provider="llm", operation=operation, outcome="invalid_response"
                ).inc()
                raise LLMGenerationError("LLM returned empty content")

            if self.json_mode and finish_reason == "length":
                if attempt < self.max_attempts:
                    json_retry = True
                    await self._retry(
                        attempt=attempt,
                        operation=operation,
                        reason="truncated_json",
                        retry_after=None,
                    )
                    continue
                PROVIDER_REQUESTS.labels(
                    provider="llm", operation=operation, outcome="invalid_response"
                ).inc()
                raise LLMGenerationError("LLM JSON response was truncated by token limit")

            if self.json_mode:
                try:
                    json.loads(content)
                except json.JSONDecodeError as exc:
                    if attempt < self.max_attempts:
                        json_retry = True
                        await self._retry(
                            attempt=attempt,
                            operation=operation,
                            reason="invalid_json",
                            retry_after=None,
                        )
                        continue
                    PROVIDER_REQUESTS.labels(
                        provider="llm", operation=operation, outcome="invalid_response"
                    ).inc()
                    raise LLMGenerationError("LLM returned invalid JSON content") from exc

            PROVIDER_REQUESTS.labels(
                provider="llm", operation=operation, outcome="success"
            ).inc()
            return content.strip()

        opened = await self._breaker.record_transient_failure()
        if opened:
            PROVIDER_CIRCUIT_OPEN.labels(provider="llm", event="opened").inc()
        PROVIDER_REQUESTS.labels(
            provider="llm", operation=operation, outcome="transient_failure"
        ).inc()
        if transient_error is None:
            transient_error = RuntimeError(transient_reason)
        raise LLMGenerationError(
            f"LLM request failed after {self.max_attempts} attempts ({transient_reason})"
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
            provider="llm", operation=operation, reason=reason
        ).inc()
        delay = await sleep_before_retry(
            attempt,
            base_seconds=self.retry_base_seconds,
            max_seconds=self.retry_max_seconds,
            retry_after=retry_after,
            sleep=self._sleep,
        )
        PROVIDER_RETRY_DELAY.labels(provider="llm", operation=operation).observe(delay)
