from typing import Protocol

import httpx


class LLMConfigurationError(RuntimeError):
    pass


class LLMGenerationError(RuntimeError):
    pass


class LLMProvider(Protocol):
    model_name: str

    async def complete(self, system_prompt: str, user_prompt: str) -> str: ...

    async def close(self) -> None: ...


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
    ) -> None:
        if not base_url.strip():
            raise LLMConfigurationError("LLM_BASE_URL is required")
        if not model_name.strip():
            raise LLMConfigurationError("LLM_MODEL is required")

        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        headers = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(
            base_url=f"{base_url.rstrip('/')}/",
            headers=headers,
            timeout=timeout,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = await self._client.post(
            "chat/completions",
            json={
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            },
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise LLMGenerationError(
                f"LLM request failed with status {response.status_code}"
            ) from exc

        try:
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMGenerationError("Unexpected LLM response shape") from exc
        if not isinstance(content, str) or not content.strip():
            raise LLMGenerationError("LLM returned empty content")
        return content.strip()
