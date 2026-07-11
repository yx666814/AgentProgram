from pathlib import Path

import pytest
from sqlalchemy import text

from agent_platform.infrastructure.database.session import create_database


@pytest.mark.asyncio
async def test_sqlite_uses_required_pragmas(tmp_path: Path) -> None:
    database = create_database(tmp_path / "agent.db")

    async with database.engine.connect() as connection:
        journal_mode = (await connection.execute(text("PRAGMA journal_mode"))).scalar_one()
        foreign_keys = (await connection.execute(text("PRAGMA foreign_keys"))).scalar_one()
        busy_timeout = (await connection.execute(text("PRAGMA busy_timeout"))).scalar_one()
        synchronous = (await connection.execute(text("PRAGMA synchronous"))).scalar_one()
        temp_store = (await connection.execute(text("PRAGMA temp_store"))).scalar_one()

    await database.dispose()

    assert str(journal_mode).lower() == "wal"
    assert foreign_keys == 1
    assert busy_timeout == 5_000
    assert synchronous == 1  # NORMAL
    assert temp_store == 2  # MEMORY
