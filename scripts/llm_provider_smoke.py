#!/usr/bin/env python3
"""Fail fast when the configured OpenAI-compatible quality provider is unusable."""

from __future__ import annotations

import asyncio
import os
import sys

from app.generation.llm import OpenAICompatibleLLM


def require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


async def run() -> None:
    base_url = require("LLM_BASE_URL")
    api_key = require("LLM_API_KEY")
    model = require("LLM_MODEL")

    provider = OpenAICompatibleLLM(
        base_url=base_url,
        api_key=api_key,
        model_name=model,
        timeout=20.0,
        temperature=0.0,
        max_tokens=16,
        max_attempts=1,
    )
    try:
        response = await provider.complete(
            "This is a connectivity probe. Reply with a short acknowledgement.",
            "Reply READY.",
        )
        if not response.strip():
            raise RuntimeError("LLM provider returned empty content")
    finally:
        await provider.close()

    print(f"LLM provider smoke: PASS (model={model!r}, response_chars={len(response)})")


def main() -> int:
    asyncio.run(run())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"LLM provider smoke: FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
