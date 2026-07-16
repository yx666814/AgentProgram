import json

import httpx
import pytest
from pydantic import SecretStr

from agent_platform.infrastructure.model_runtime import DesktopHttpSecretStore


@pytest.mark.asyncio
async def test_desktop_secret_store_resolves_only_valid_authenticated_values() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = json.loads(request.content)
        if payload["credential_ref"] == "credential.xingxie.missing":
            return httpx.Response(200, json={"value": None})
        return httpx.Response(200, json={"value": "resolved-api-key"})

    store = DesktopHttpSecretStore(
        "http://127.0.0.1:54321",
        SecretStr("bridge-secret"),
        transport=httpx.MockTransport(handler),
    )

    assert await store.resolve("credential.xingxie.primary") == "resolved-api-key"
    assert await store.resolve("credential.xingxie.missing") is None
    assert await store.resolve("INVALID REF") is None
    assert len(requests) == 2
    assert requests[0].headers["authorization"] == "Bearer bridge-secret"
    assert "bridge-secret" not in repr(store)


@pytest.mark.asyncio
async def test_desktop_secret_store_rejects_invalid_bridge_responses() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"value": "", "extra": True})

    store = DesktopHttpSecretStore(
        "http://127.0.0.1:54321",
        SecretStr("bridge-secret"),
        transport=httpx.MockTransport(handler),
    )

    assert await store.resolve("credential.xingxie.primary") is None
