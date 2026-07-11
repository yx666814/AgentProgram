from agent_platform.infrastructure.logging.configure import redact_secrets


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
