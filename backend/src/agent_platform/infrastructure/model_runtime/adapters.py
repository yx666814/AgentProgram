from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

import httpx

from agent_platform.domain.model_runtime import (
    ModelChunk,
    ModelInvocation,
    ModelMessageRole,
    ModelProvider,
)
from agent_platform.ports.model_runtime import ModelAdapterError


class OpenAICompatibleAdapter:
    def __init__(
        self, client: httpx.AsyncClient | None = None, *, timeout_seconds: float = 120
    ) -> None:
        self._client = client
        self._timeout_seconds = timeout_seconds

    @property
    def provider(self) -> ModelProvider:
        return ModelProvider.OPENAI_COMPATIBLE

    async def stream(
        self,
        invocation: ModelInvocation,
        *,
        base_url: str,
        api_key: str,
        cancellation: asyncio.Event,
    ) -> AsyncIterator[ModelChunk]:
        body = {
            "model": invocation.model,
            "messages": [message.model_dump(mode="json") for message in invocation.messages],
            "max_tokens": invocation.max_output_tokens,
            "temperature": invocation.temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        client = self._client or httpx.AsyncClient(timeout=self._timeout_seconds)
        try:
            async with client.stream(
                "POST",
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=body,
            ) as response:
                response.raise_for_status()
                async for line in _cancel_aware_lines(response, cancellation):
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    document = _json_object(payload)
                    text = _openai_text(document)
                    usage = document.get("usage")
                    if text:
                        yield ModelChunk(text=text)
                    if isinstance(usage, dict):
                        yield ModelChunk(
                            input_tokens=_nonnegative_int(usage.get("prompt_tokens")),
                            output_tokens=_nonnegative_int(usage.get("completion_tokens")),
                        )
        except asyncio.CancelledError:
            raise
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            raise ModelAdapterError("model.openai_request_failed") from None
        finally:
            if self._client is None:
                await client.aclose()


class AnthropicAdapter:
    def __init__(
        self, client: httpx.AsyncClient | None = None, *, timeout_seconds: float = 120
    ) -> None:
        self._client = client
        self._timeout_seconds = timeout_seconds

    @property
    def provider(self) -> ModelProvider:
        return ModelProvider.ANTHROPIC

    async def stream(
        self,
        invocation: ModelInvocation,
        *,
        base_url: str,
        api_key: str,
        cancellation: asyncio.Event,
    ) -> AsyncIterator[ModelChunk]:
        system_parts = [
            message.content
            for message in invocation.messages
            if message.role is ModelMessageRole.SYSTEM
        ]
        messages = [
            message.model_dump(mode="json")
            for message in invocation.messages
            if message.role is not ModelMessageRole.SYSTEM
        ]
        body = {
            "model": invocation.model,
            "system": "\n\n".join(system_parts),
            "messages": messages,
            "max_tokens": invocation.max_output_tokens,
            "temperature": invocation.temperature,
            "stream": True,
        }
        client = self._client or httpx.AsyncClient(timeout=self._timeout_seconds)
        try:
            async with client.stream(
                "POST",
                f"{base_url}/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                json=body,
            ) as response:
                response.raise_for_status()
                async for line in _cancel_aware_lines(response, cancellation):
                    if not line.startswith("data:"):
                        continue
                    document = _json_object(line[5:].strip())
                    event_type = document.get("type")
                    if event_type == "content_block_delta":
                        delta = document.get("delta")
                        if isinstance(delta, dict) and isinstance(delta.get("text"), str):
                            yield ModelChunk(text=delta["text"])
                    elif event_type == "message_start":
                        message = document.get("message")
                        usage = message.get("usage") if isinstance(message, dict) else None
                        if isinstance(usage, dict):
                            yield ModelChunk(
                                input_tokens=_nonnegative_int(usage.get("input_tokens")),
                                output_tokens=0,
                            )
                    elif event_type == "message_delta":
                        usage = document.get("usage")
                        if isinstance(usage, dict):
                            yield ModelChunk(
                                input_tokens=0,
                                output_tokens=_nonnegative_int(usage.get("output_tokens")),
                            )
        except asyncio.CancelledError:
            raise
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            raise ModelAdapterError("model.anthropic_request_failed") from None
        finally:
            if self._client is None:
                await client.aclose()


@dataclass(frozen=True, slots=True)
class FakeModelScript:
    chunks: tuple[str, ...]
    input_tokens: int = 1
    output_tokens: int = 1
    error_code: str | None = None
    delay_seconds: float = 0.0


class ScriptedFakeModelAdapter:
    def __init__(self, scripts: tuple[FakeModelScript, ...]) -> None:
        self._scripts = list(scripts)
        self.invocations: list[ModelInvocation] = []
        self.cancellation_observed = False

    @property
    def provider(self) -> ModelProvider:
        return ModelProvider.FAKE

    async def stream(
        self,
        invocation: ModelInvocation,
        *,
        base_url: str,
        api_key: str,
        cancellation: asyncio.Event,
    ) -> AsyncIterator[ModelChunk]:
        del base_url, api_key
        if not self._scripts:
            raise ModelAdapterError("model.fake_script_exhausted")
        script = self._scripts.pop(0)
        self.invocations.append(invocation)
        for chunk in script.chunks:
            if cancellation.is_set():
                self.cancellation_observed = True
                raise asyncio.CancelledError
            if script.delay_seconds:
                try:
                    await _cancel_aware_sleep(script.delay_seconds, cancellation)
                except asyncio.CancelledError:
                    self.cancellation_observed = True
                    raise
            yield ModelChunk(text=chunk)
        if script.error_code is not None:
            raise ModelAdapterError(script.error_code)
        yield ModelChunk(
            input_tokens=script.input_tokens,
            output_tokens=script.output_tokens,
        )


async def _cancel_aware_lines(
    response: httpx.Response,
    cancellation: asyncio.Event,
) -> AsyncIterator[str]:
    iterator = response.aiter_lines()
    while True:
        if cancellation.is_set():
            raise asyncio.CancelledError
        next_line: asyncio.Future[str] = asyncio.ensure_future(anext(iterator))
        cancelled = asyncio.create_task(cancellation.wait())
        done, _ = await asyncio.wait(
            (next_line, cancelled),
            return_when=asyncio.FIRST_COMPLETED,
        )
        if cancelled in done and cancellation.is_set():
            next_line.cancel()
            with suppress(asyncio.CancelledError, StopAsyncIteration):
                await next_line
            raise asyncio.CancelledError
        cancelled.cancel()
        with suppress(asyncio.CancelledError):
            await cancelled
        try:
            yield next_line.result()
        except StopAsyncIteration:
            return


async def _cancel_aware_sleep(delay: float, cancellation: asyncio.Event) -> None:
    try:
        await asyncio.wait_for(cancellation.wait(), timeout=delay)
    except TimeoutError:
        return
    raise asyncio.CancelledError


def _json_object(payload: str) -> dict[str, Any]:
    document = json.loads(payload)
    if not isinstance(document, dict):
        raise ValueError("provider event must be an object")
    return document


def _openai_text(document: dict[str, Any]) -> str:
    choices = document.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    choice = choices[0]
    if not isinstance(choice, dict):
        return ""
    delta = choice.get("delta")
    if not isinstance(delta, dict):
        return ""
    content = delta.get("content")
    return content if isinstance(content, str) else ""


def _nonnegative_int(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("usage token count is invalid")
    return value
