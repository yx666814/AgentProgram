import io
import os
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

import agent_platform.desktop as desktop_module
from agent_platform.config.settings import Settings
from agent_platform.desktop import ensure_desktop_database, read_desktop_settings
from agent_platform.infrastructure.database.backup import BackupReason, create_verified_backup
from agent_platform.infrastructure.database.schema import CURRENT_DATABASE_REVISION


def test_desktop_startup_frame_builds_hidden_settings(tmp_path: Path) -> None:
    token = "desktop-startup-secret"
    frame = io.StringIO(
        "{"
        '"protocol_version":1,'
        f'"session_token":"{token}",'
        f'"data_root":"{tmp_path.as_posix()}",'
        f'"parent_pid":{os.getpid()},'
        '"secret_bridge_origin":"http://127.0.0.1:54321",'
        '"secret_bridge_token":"bridge-secret",'
        '"host":"127.0.0.1",'
        '"port":0'
        "}\n"
    )

    launch = read_desktop_settings(frame)

    assert launch.parent_pid == os.getpid()
    assert launch.settings.data_root == tmp_path
    assert launch.settings.port == 0
    assert launch.settings.session_token == token
    assert token not in repr(launch.settings)
    assert token not in str(launch.settings.model_dump())


@pytest.mark.parametrize(
    "serialized",
    [
        "{}",
        "{}\n",
        '{"protocol_version":1,"session_token":""}\n',
        "x" * 4097 + "\n",
    ],
)
def test_desktop_startup_frame_rejects_invalid_input(serialized: str) -> None:
    with pytest.raises(RuntimeError, match="desktop startup frame"):
        read_desktop_settings(io.StringIO(serialized))


def test_desktop_database_migrates_to_current_revision(tmp_path: Path) -> None:
    settings = Settings(data_root=tmp_path, session_token="desktop-migration-secret")
    backend_root = Path(__file__).resolve().parents[2]

    ensure_desktop_database(settings, backend_root=backend_root)
    ensure_desktop_database(settings, backend_root=backend_root)

    with sqlite3.connect(settings.database_path) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    assert revision == (CURRENT_DATABASE_REVISION,)


def test_desktop_database_restores_pre_migration_backup_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(data_root=tmp_path, session_token="desktop-migration-secret")
    backend_root = Path(__file__).resolve().parents[2]
    ensure_desktop_database(settings, backend_root=backend_root)
    with closing(sqlite3.connect(settings.database_path)) as connection:
        connection.execute("UPDATE alembic_version SET version_num = '0008_model_runtime'")
        connection.commit()

    def fail_upgrade(*_: object) -> None:
        create_verified_backup(
            settings.database_path,
            settings.backup_root,
            reason=BackupReason.PRE_MIGRATION,
        )
        with closing(sqlite3.connect(settings.database_path)) as connection:
            connection.execute(
                "CREATE TABLE desktop_partial_migration_marker (id INTEGER PRIMARY KEY)"
            )
            connection.commit()
        raise RuntimeError("simulated migration failure")

    monkeypatch.setattr(desktop_module.command, "upgrade", fail_upgrade)

    with pytest.raises(RuntimeError, match="previous backup was restored"):
        ensure_desktop_database(settings, backend_root=backend_root)

    with closing(sqlite3.connect(settings.database_path)) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        marker = connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type='table' AND name='desktop_partial_migration_marker'"
        ).fetchone()
    assert revision == ("0008_model_runtime",)
    assert marker is None
