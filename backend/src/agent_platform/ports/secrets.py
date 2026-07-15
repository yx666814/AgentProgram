from typing import Protocol


class SecretStore(Protocol):
    async def resolve(self, credential_ref: str) -> str | None: ...
