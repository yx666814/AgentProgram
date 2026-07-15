from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Protocol

from agent_platform.domain.model_runtime import ModelChunk, ModelInvocation, ModelProvider


class ModelAdapterError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ModelAdapter(Protocol):
    @property
    def provider(self) -> ModelProvider: ...

    def stream(
        self,
        invocation: ModelInvocation,
        *,
        base_url: str,
        api_key: str,
        cancellation: asyncio.Event,
    ) -> AsyncIterator[ModelChunk]: ...
