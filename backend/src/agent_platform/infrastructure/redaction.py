from __future__ import annotations

import math
import threading
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

SENSITIVE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "api_key",
        "authorization",
        "credential",
        "password",
        "secret",
        "session_token",
        "token",
    }
)

_LOCK = threading.RLock()
_KNOWN_SECRETS: Counter[str] = Counter()


@dataclass(slots=True)
class SecretRegistration:
    _value: str = field(repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    def close(self) -> None:
        with _LOCK:
            if self._closed:
                return
            self._closed = True
            count = _KNOWN_SECRETS.get(self._value, 0)
            if count <= 1:
                _KNOWN_SECRETS.pop(self._value, None)
            else:
                _KNOWN_SECRETS[self._value] = count - 1


def register_known_secret(value: str) -> SecretRegistration:
    if not value.strip():
        raise ValueError("known secret must not be empty")
    with _LOCK:
        _KNOWN_SECRETS[value] += 1
    return SecretRegistration(value)


def redact_text(value: str) -> str:
    with _LOCK:
        secrets = sorted(_KNOWN_SECRETS, key=len, reverse=True)
    for secret in secrets:
        value = value.replace(secret, "***")
    return value


def _sanitize(value: object, *, key: str | None = None) -> object:
    if key is not None and key.lower() in SENSITIVE_KEYS:
        return "***"
    if isinstance(value, str):
        return redact_text(value)
    if value is None or type(value) in {bool, int}:
        return value
    if type(value) is float:
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return sanitize_mapping(value)
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize(item) for item in value)
    return None


def sanitize_mapping(value: Mapping[Any, Any]) -> dict[str, object]:
    return {
        str(item_key): _sanitize(item_value, key=str(item_key))
        for item_key, item_value in value.items()
    }
