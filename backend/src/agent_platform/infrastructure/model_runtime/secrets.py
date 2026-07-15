from __future__ import annotations


class UnavailableSecretStore:
    async def resolve(self, credential_ref: str) -> str | None:
        del credential_ref
        return None


class InMemorySecretStore:
    def __init__(self, secrets: dict[str, str] | None = None) -> None:
        self._secrets = dict(secrets or {})

    def set(self, credential_ref: str, value: str) -> None:
        if not credential_ref or not value:
            raise ValueError("credential reference and value must not be empty")
        self._secrets[credential_ref] = value

    async def resolve(self, credential_ref: str) -> str | None:
        return self._secrets.get(credential_ref)
