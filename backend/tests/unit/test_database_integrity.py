import sqlite3
from pathlib import Path

import pytest

from agent_platform.infrastructure.database.integrity import (
    DatabaseIntegrityError,
    IntegrityCheckMode,
    WalCheckpointMode,
    check_database_integrity,
    checkpoint_database,
    require_database_integrity,
)


@pytest.mark.asyncio
async def test_integrity_and_checkpoint_report_healthy_database(tmp_path: Path) -> None:
    path = tmp_path / "agent.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE values_table (value INTEGER NOT NULL)")
        connection.execute("INSERT INTO values_table VALUES (1)")
        connection.execute("PRAGMA journal_mode=WAL")

    result = await check_database_integrity(path, IntegrityCheckMode.QUICK, 5)
    checkpoint = await checkpoint_database(path, WalCheckpointMode.PASSIVE, 5)

    assert result.ok is True
    assert checkpoint.busy == 0


@pytest.mark.asyncio
async def test_require_integrity_rejects_corrupt_database_without_path_leak(tmp_path: Path) -> None:
    path = tmp_path / "secret-agent.db"
    path.write_bytes(b"not a sqlite database")

    with pytest.raises(DatabaseIntegrityError) as raised:
        await require_database_integrity(path, IntegrityCheckMode.QUICK, 5)

    assert str(path) not in str(raised.value)
