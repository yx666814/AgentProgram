import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest

from agent_platform.infrastructure.database.maintenance import DatabaseMaintenance


@pytest.mark.asyncio
async def test_database_maintenance_forces_integrity_backup_and_checkpoint(tmp_path: Path) -> None:
    database_path = tmp_path / "data" / "agent.db"
    database_path.parent.mkdir()
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE alembic_version (version_num TEXT NOT NULL)")
        connection.execute("INSERT INTO alembic_version VALUES ('0001_foundation')")
        connection.execute("CREATE TABLE sample (value INTEGER NOT NULL)")
    log_root = tmp_path / "logs"
    log_root.mkdir()
    maintenance = DatabaseMaintenance(
        database_path=database_path,
        backup_root=tmp_path / "backups",
        log_root=log_root,
        operation_timeout_seconds=5,
        maintenance_interval_seconds=60,
        integrity_interval_seconds=60,
        backup_interval_seconds=60,
        backup_retain_count=2,
        backup_retention_age=timedelta(days=30),
        log_retention_age=timedelta(days=30),
        max_entries_per_run=100,
        size_warning_bytes=1024 * 1024,
    )

    await maintenance.run_once(force_integrity=True, force_backup=True)
    await maintenance.final_checkpoint()

    assert maintenance.snapshot.last_integrity_check_at is not None
    assert maintenance.snapshot.last_backup_at is not None
    assert maintenance.snapshot.checkpoint_busy is False
    assert list((tmp_path / "backups").glob("*.manifest.json"))
