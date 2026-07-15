from __future__ import annotations

import re
from typing import Any

import httpx
from pydantic import SecretStr

_CREDENTIAL_REF = re.compile(r"^[a-z][a-z0-9_.:-]{2,127}$")


class DesktopHttpSecretStore:
    def __init__(
        self,
        origin: str,
        token: SecretStr,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._origin = origin.rstrip("/")
        self._token = token
        self._transport = transport

    async def resolve(self, credential_ref: str) -> str | None:
        if _CREDENTIAL_REF.fullmatch(credential_ref) is None:
            return None
        try:
            async with httpx.AsyncClient(
                base_url=self._origin,
                timeout=5.0,
                follow_redirects=False,
                trust_env=False,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    "/v1/resolve",
                    headers={
                        "Authorization": f"Bearer {self._token.get_secret_value()}",
                        "Accept": "application/json",
                    },
                    json={"credential_ref": credential_ref},
                )
                if response.status_code != 200:
                    return None
                payload: Any = response.json()
        except (httpx.HTTPError, TypeError, ValueError):
            return None
        if not isinstance(payload, dict) or set(payload) != {"value"}:
            return None
        value = payload["value"]
        if value is None:
            return None
        if not isinstance(value, str) or not value or len(value) > 16_384:
            return None
        return value
