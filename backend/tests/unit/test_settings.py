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


@pytest.mark.parametrize(
    "interval",
    [0.0, -0.1, float("nan"), float("inf"), float("-inf")],
)
def test_settings_rejects_invalid_watchdog_interval(
    tmp_path: Path,
    interval: float,
) -> None:
    with pytest.raises(ValidationError, match="positive finite"):
        Settings(
            data_root=tmp_path,
            session_token="local-secret",
            worker_watchdog_interval_seconds=interval,
        )


@pytest.mark.parametrize(
    "interval",
    [0.0, -0.1, float("nan"), float("inf"), float("-inf")],
)
def test_settings_rejects_invalid_heartbeat_timeout(
    tmp_path: Path,
    interval: float,
) -> None:
    with pytest.raises(ValidationError, match="positive finite"):
        Settings(
            data_root=tmp_path,
            session_token="local-secret",
            worker_heartbeat_timeout_seconds=interval,
        )


def test_settings_accepts_valid_watchdog_interval(tmp_path: Path) -> None:
    settings = Settings(
        data_root=tmp_path,
        session_token="local-secret",
        worker_watchdog_interval_seconds=0.5,
    )

    assert settings.worker_watchdog_interval_seconds == 0.5


def test_watchdog_interval_must_be_shorter_than_heartbeat_timeout(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="shorter than heartbeat timeout"):
        Settings(
            data_root=tmp_path,
            session_token="local-secret",
            worker_watchdog_interval_seconds=15.0,
            worker_heartbeat_timeout_seconds=15.0,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("log_file_max_bytes", 1024),
        ("log_record_max_bytes", 512),
        ("log_file_retained_count", 0),
        ("log_file_retention_days", 0),
        ("log_queue_capacity", 1),
        ("log_shutdown_drain_seconds", 0.0),
    ],
)
def test_settings_rejects_invalid_logging_bounds(
    tmp_path: Path,
    field: str,
    value: int | float,
) -> None:
    with pytest.raises(ValidationError):
        Settings(
            data_root=tmp_path,
            session_token="local-secret",
            **{field: value},
        )


def test_settings_exposes_logging_durations(tmp_path: Path) -> None:
    settings = Settings(
        data_root=tmp_path,
        session_token="local-secret",
        log_file_retention_days=7,
        log_shutdown_drain_seconds=0.5,
    )

    assert settings.log_file_retention_age.total_seconds() == 7 * 24 * 60 * 60
    assert settings.log_shutdown_drain_timeout.total_seconds() == 0.5


@pytest.mark.parametrize("capacity", [63, 65_537])
def test_settings_rejects_invalid_ipc_replay_capacity(tmp_path: Path, capacity: int) -> None:
    with pytest.raises(ValidationError):
        Settings(
            data_root=tmp_path,
            session_token="local-secret",
            worker_ipc_replay_window_capacity=capacity,
        )


def test_database_maintenance_interval_must_fit_scheduled_work(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="database maintenance interval"):
        Settings(
            data_root=tmp_path,
            session_token="local-secret",
            database_maintenance_interval_seconds=120,
            database_integrity_check_interval_seconds=60,
        )
