import asyncio
import json

import httpx
import pytest

from agent_platform.domain.model_runtime import (
    ModelInvocation,
    ModelMessage,
    ModelMessageRole,
)
from agent_platform.infrastructure.model_runtime import (
    AnthropicAdapter,
    DeterministicFakeModelAdapter,
    OpenAICompatibleAdapter,
)


def _invocation() -> ModelInvocation:
    return ModelInvocation(
        model="test-model",
        messages=(ModelMessage(role=ModelMessageRole.USER, content="hello"),),
    )


@pytest.mark.asyncio
async def test_openai_compatible_adapter_parses_text_and_usage() -> None:
    body = "\n".join(
        (
            f"data: {json.dumps({'choices': [{'delta': {'content': 'hello'}}]})}",
            "data: "
            + json.dumps({"choices": [], "usage": {"prompt_tokens": 2, "completion_tokens": 3}}),
            "data: [DONE]",
            "",
        )
    )
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text=body))
    )
    try:
        chunks = [
            chunk
            async for chunk in OpenAICompatibleAdapter(client).stream(
                _invocation(),
                base_url="https://models.example/v1",
                api_key="secret-not-logged",
                cancellation=asyncio.Event(),
            )
        ]
    finally:
        await client.aclose()

    assert "".join(chunk.text for chunk in chunks) == "hello"
    assert (chunks[-1].input_tokens, chunks[-1].output_tokens) == (2, 3)


@pytest.mark.asyncio
async def test_anthropic_adapter_parses_text_and_split_usage() -> None:
    events = (
        {"type": "message_start", "message": {"usage": {"input_tokens": 4}}},
        {"type": "content_block_delta", "delta": {"text": "answer"}},
        {"type": "message_delta", "usage": {"output_tokens": 5}},
    )
    body = "\n".join(f"data: {json.dumps(event)}" for event in events)
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text=body))
    )
    try:
        chunks = [
            chunk
            async for chunk in AnthropicAdapter(client).stream(
                _invocation(),
                base_url="https://api.anthropic.com/v1",
                api_key="secret-not-logged",
                cancellation=asyncio.Event(),
            )
        ]
    finally:
        await client.aclose()

    assert "".join(chunk.text for chunk in chunks) == "answer"
    assert sum(chunk.input_tokens or 0 for chunk in chunks) == 4
    assert sum(chunk.output_tokens or 0 for chunk in chunks) == 5


@pytest.mark.asyncio
async def test_deterministic_fake_adapter_is_available_without_network() -> None:
    chunks = [
        chunk
        async for chunk in DeterministicFakeModelAdapter().stream(
            _invocation(),
            base_url="https://fake.invalid/v1",
            api_key="ignored-fake-credential",
            cancellation=asyncio.Event(),
        )
    ]

    assert "deterministic local response" in "".join(chunk.text for chunk in chunks)
    assert chunks[-1].input_tokens is not None
    assert chunks[-1].output_tokens is not None
