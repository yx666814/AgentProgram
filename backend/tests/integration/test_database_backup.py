import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agent_platform.infrastructure.database.backup import (
    BackupReason,
    BackupVerificationError,
    create_verified_backup,
    prune_backup_root,
    restore_verified_backup,
    verify_backup,
)


def _database(path: Path, value: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE alembic_version (version_num TEXT NOT NULL)")
        connection.execute("INSERT INTO alembic_version VALUES ('0001_foundation')")
        connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample VALUES (?)", (value,))


def test_verified_backup_round_trips_and_rejects_corruption(tmp_path: Path) -> None:
    source = tmp_path / "agent.db"
    backups = tmp_path / "backups"
    restored = tmp_path / "restored.db"
    _database(source, "original")

    backup = create_verified_backup(source, backups, reason=BackupReason.MANUAL)

    assert verify_backup(backup.manifest_path).manifest.schema_revision == "0001_foundation"
    restore_verified_backup(backup.manifest_path, restored)
    with sqlite3.connect(restored) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone() == ("original",)

    manifest = json.loads(backup.manifest_path.read_text(encoding="utf-8"))
    manifest["sha256"] = "0" * 64
    backup.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(BackupVerificationError):
        verify_backup(backup.manifest_path)


def test_backup_retention_keeps_newest_valid_pair(tmp_path: Path) -> None:
    source = tmp_path / "agent.db"
    backups = tmp_path / "backups"
    _database(source, "original")
    old = create_verified_backup(
        source,
        backups,
        reason=BackupReason.SCHEDULED,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    newest = create_verified_backup(
        source,
        backups,
        reason=BackupReason.SCHEDULED,
        now=datetime(2026, 2, 1, tzinfo=UTC),
    )

    prune_backup_root(
        backups,
        retain_count=1,
        retention_age=timedelta(days=1),
        max_entries=100,
        now=datetime(2026, 3, 1, tzinfo=UTC),
    )

    assert newest.manifest_path.exists()
    assert newest.database_path.exists()
    assert not old.manifest_path.exists()
    assert not old.database_path.exists()
