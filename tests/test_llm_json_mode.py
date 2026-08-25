import json

import httpx

from app.generation.llm import OpenAICompatibleLLM


async def _no_sleep(_delay: float) -> None:
    return None


async def test_json_mode_requests_json_object_and_retries_invalid_json() -> None:
    attempts = 0
    request_bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        request_bodies.append(json.loads(request.content))
        if attempts == 1:
            return httpx.Response(
                200,
                request=request,
                json={
                    "choices": [
                        {"message": {"content": "not valid json"}, "finish_reason": "stop"}
                    ]
                },
            )
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [
                    {"message": {"content": '{"answer":"ok"}'}, "finish_reason": "stop"}
                ]
            },
        )

    llm = OpenAICompatibleLLM(
        base_url="https://llm.example/v1",
        model_name="test-model",
        json_mode=True,
        max_attempts=2,
        retry_base_seconds=0,
        retry_max_seconds=0.1,
        transport=httpx.MockTransport(handler),
        sleep=_no_sleep,
    )
    try:
        result = await llm.complete("Return JSON.", "Question")
    finally:
        await llm.close()

    assert result == '{"answer":"ok"}'
    assert attempts == 2
    assert request_bodies[0]["response_format"] == {"type": "json_object"}
    retry_messages = request_bodies[1]["messages"]
    assert isinstance(retry_messages, list)
    assert "compact valid JSON" in retry_messages[0]["content"]


async def test_json_mode_retries_truncated_completion() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(
                200,
                request=request,
                json={
                    "choices": [
                        {"message": {"content": '{"answer":"cut'}, "finish_reason": "length"}
                    ]
                },
            )
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [
                    {"message": {"content": '{"answer":"ok"}'}, "finish_reason": "stop"}
                ]
            },
        )

    llm = OpenAICompatibleLLM(
        base_url="https://llm.example/v1",
        model_name="test-model",
        json_mode=True,
        max_attempts=2,
        retry_base_seconds=0,
        retry_max_seconds=0.1,
        transport=httpx.MockTransport(handler),
        sleep=_no_sleep,
    )
    try:
        result = await llm.complete("Return JSON.", "Question")
    finally:
        await llm.close()

    assert result == '{"answer":"ok"}'
    assert attempts == 2


async def test_plain_mode_keeps_unstructured_provider_calls_compatible() -> None:
    request_body: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        request_body.update(json.loads(request.content))
        return httpx.Response(
            200,
            request=request,
            json={"choices": [{"message": {"content": "READY"}, "finish_reason": "stop"}]},
        )

    llm = OpenAICompatibleLLM(
        base_url="https://llm.example/v1",
        model_name="test-model",
        transport=httpx.MockTransport(handler),
    )
    try:
        result = await llm.complete("Reply briefly.", "READY")
    finally:
        await llm.close()

    assert result == "READY"
    assert "response_format" not in request_body
