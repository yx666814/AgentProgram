import json
import logging
from collections.abc import Iterator
from io import StringIO
from pathlib import Path

import pytest
import structlog

from agent_platform.infrastructure.logging.configure import configure_logging, redact_secrets


@pytest.fixture
def isolated_logging() -> Iterator[logging.Logger]:
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers.copy()
    original_level = root_logger.level
    original_structlog_config = structlog.get_config()
    root_logger.handlers.clear()

    try:
        yield root_logger
    finally:
        for handler in root_logger.handlers:
            handler.close()
        root_logger.handlers.clear()
        root_logger.handlers.extend(original_handlers)
        root_logger.setLevel(original_level)
        structlog.configure(**original_structlog_config)


def test_redact_secrets_masks_nested_credentials() -> None:
    event = {
        "authorization": "Bearer abc",
        "api_key": "sk-secret",
        "nested": {"token": "hidden", "safe": "value"},
    }

    redacted = redact_secrets(None, "info", event)

    assert redacted["authorization"] == "***"
    assert redacted["api_key"] == "***"
    assert redacted["nested"]["token"] == "***"
    assert redacted["nested"]["safe"] == "value"


def test_redact_secrets_masks_credentials_in_tuples_without_mutating_input() -> None:
    event = {"items": ({"TOKEN": "tuple-secret", "safe": "ok"},)}

    redacted = redact_secrets(None, "info", event)

    assert isinstance(redacted["items"], tuple)
    assert redacted["items"][0]["TOKEN"] == "***"
    assert redacted["items"][0]["safe"] == "ok"
    assert event == {"items": ({"TOKEN": "tuple-secret", "safe": "ok"},)}


def test_configure_logging_renders_redacted_stdlib_extras_as_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    isolated_logging: logging.Logger,
) -> None:
    configure_logging(tmp_path / "logs", "INFO")

    logging.getLogger("stdlib-test").info(
        "stdlib event",
        extra={"token": "stdlib-secret", "safe": "ok"},
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip().startswith("{")
    event = json.loads(captured.err)
    assert event["token"] == "***"
    assert event["safe"] == "ok"


def test_configure_logging_routes_native_structlog_through_root_handler(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    isolated_logging: logging.Logger,
) -> None:
    configure_logging(tmp_path / "logs", "INFO")

    structlog.get_logger("structlog-test").info(
        "structlog event",
        token="structlog-secret",
        safe="ok",
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    event = json.loads(captured.err)
    assert event["token"] == "***"
    assert event["safe"] == "ok"


def test_configure_logging_replaces_existing_root_configuration(
    tmp_path: Path,
    isolated_logging: logging.Logger,
) -> None:
    existing_handler = logging.StreamHandler(StringIO())
    isolated_logging.addHandler(existing_handler)
    isolated_logging.setLevel(logging.WARNING)

    configure_logging(tmp_path / "logs", "DEBUG")

    assert isolated_logging.level == logging.DEBUG
    assert isolated_logging.handlers != [existing_handler]
    assert len(isolated_logging.handlers) == 1


def test_configure_logging_validates_level_before_creating_log_root(
    tmp_path: Path,
    isolated_logging: logging.Logger,
) -> None:
    log_root = tmp_path / "logs"

    with pytest.raises(ValueError, match="invalid log level"):
        configure_logging(log_root, "verbose")

    assert not log_root.exists()
