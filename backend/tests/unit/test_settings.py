from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_platform.config.settings import Settings


def test_settings_builds_all_application_directories(tmp_path: Path) -> None:
    settings = Settings(data_root=tmp_path, session_token="secret")

    assert settings.database_path == tmp_path / "data" / "agent.db"
    assert settings.snapshot_root == tmp_path / "snapshots"
    assert settings.log_root == tmp_path / "logs"
    assert settings.backup_root == tmp_path / "backups"
    assert settings.runtime_root == tmp_path / "runtime"


def test_settings_rejects_empty_session_token(tmp_path: Path) -> None:
    try:
        Settings(data_root=tmp_path, session_token="")
    except ValueError as exc:
        rendered_error = str(exc)
        debug_error = repr(exc)
        assert "session_token" in rendered_error
        assert "input_value" not in rendered_error
        assert "input_value" not in debug_error
    else:
        raise AssertionError("empty session token must fail")


def test_settings_rejects_non_ascii_session_token(tmp_path: Path) -> None:
    invalid_token = "秘密-setting-token"
    try:
        Settings(data_root=tmp_path, session_token=invalid_token)
    except ValueError as exc:
        rendered_error = str(exc)
        debug_error = repr(exc)
        assert "session_token" in rendered_error
        assert "ASCII" in rendered_error
        assert invalid_token not in rendered_error
        assert invalid_token not in debug_error
        assert "input_value" not in rendered_error
        assert "input_value" not in debug_error
    else:
        raise AssertionError("non-ASCII session token must fail")


def test_settings_hides_session_token_from_repr_and_dump(tmp_path: Path) -> None:
    settings = Settings(data_root=tmp_path, session_token="super-secret")

    assert "super-secret" not in repr(settings)
    assert "session_token" not in settings.model_dump()
    assert settings.session_token == "super-secret"


def test_settings_rejects_non_loopback_host(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        Settings(
            host="0.0.0.0",
            data_root=tmp_path,
            session_token="local-secret",
        )


@pytest.mark.parametrize("port", [-1, 65536])
def test_settings_rejects_invalid_port(tmp_path: Path, port: int) -> None:
    with pytest.raises(ValidationError):
        Settings(data_root=tmp_path, session_token="local-secret", port=port)
