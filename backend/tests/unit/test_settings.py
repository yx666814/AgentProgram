from pathlib import Path

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
        assert "session_token" in str(exc)
    else:
        raise AssertionError("empty session token must fail")


def test_settings_hides_session_token_from_repr_and_dump(tmp_path: Path) -> None:
    settings = Settings(data_root=tmp_path, session_token="super-secret")

    assert "super-secret" not in repr(settings)
    assert "session_token" not in settings.model_dump()
    assert settings.session_token == "super-secret"
