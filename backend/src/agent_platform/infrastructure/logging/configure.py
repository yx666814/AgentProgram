from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import structlog
from structlog.typing import Processor

SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "credential",
    "password",
    "secret",
    "session_token",
    "token",
}


def _redact(value: Any, key: str | None = None) -> Any:
    if key and key.lower() in SENSITIVE_KEYS:
        return "***"
    if isinstance(value, Mapping):
        return {
            item_key: _redact(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def redact_secrets(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    redacted = _redact(event_dict)
    if not isinstance(redacted, dict):
        raise TypeError("event_dict redaction must produce a dictionary")
    return redacted


def configure_logging(log_root: Path, level: str) -> None:
    log_root.mkdir(parents=True, exist_ok=True)
    numeric_level = logging.getLevelNamesMapping().get(level.upper())
    if numeric_level is None:
        raise ValueError(f"invalid log level: {level}")
    logging.basicConfig(level=numeric_level, format="%(message)s")
    structlog.configure(
        processors=[
            cast(Processor, redact_secrets),
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.PrintLoggerFactory(),
    )
