import math

import pytest

from agent_platform.infrastructure.redaction import (
    redact_text,
    register_known_secret,
    sanitize_mapping,
)


def test_registered_secret_is_removed_from_embedded_text() -> None:
    registration = register_known_secret("session-secret")
    try:
        assert redact_text("Bearer session-secret?token=session-secret") == "Bearer ***?token=***"
    finally:
        registration.close()


def test_registration_is_reference_counted_and_close_is_idempotent() -> None:
    first = register_known_secret("shared-secret")
    second = register_known_secret("shared-secret")
    first.close()
    first.close()
    assert redact_text("shared-secret") == "***"
    second.close()
    assert redact_text("shared-secret") == "shared-secret"


@pytest.mark.parametrize("value", ["", "   "])
def test_known_secret_registration_rejects_empty_values(value: str) -> None:
    with pytest.raises(ValueError, match="known secret must not be empty"):
        register_known_secret(value)


def test_sanitize_mapping_redacts_nested_values_and_unsupported_objects() -> None:
    registration = register_known_secret("known-secret")
    try:
        sanitized = sanitize_mapping(
            {
                "authorization": "Bearer known-secret",
                "safe": "prefix-known-secret",
                "nested": {"token": "hidden", "number": 3},
                "nonfinite": math.inf,
                "unsupported": object(),
            }
        )
    finally:
        registration.close()

    assert sanitized == {
        "authorization": "***",
        "safe": "prefix-***",
        "nested": {"token": "***", "number": 3},
        "nonfinite": None,
        "unsupported": None,
    }
