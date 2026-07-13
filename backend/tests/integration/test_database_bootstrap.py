import os
import subprocess
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import UniqueConstraint, select, text
from sqlalchemy.exc import StatementError

from agent_platform.infrastructure.database.base import Base
from agent_platform.infrastructure.database.models import EventLogRow
from agent_platform.infrastructure.database.session import create_database


@pytest.mark.asyncio
async def test_sqlite_uses_required_pragmas(tmp_path: Path) -> None:
    database = create_database(tmp_path / "agent.db")

    try:
        async with database.engine.connect() as connection:
            journal_mode = (await connection.execute(text("PRAGMA journal_mode"))).scalar_one()
            foreign_keys = (await connection.execute(text("PRAGMA foreign_keys"))).scalar_one()
            busy_timeout = (await connection.execute(text("PRAGMA busy_timeout"))).scalar_one()
            synchronous = (await connection.execute(text("PRAGMA synchronous"))).scalar_one()
            temp_store = (await connection.execute(text("PRAGMA temp_store"))).scalar_one()
    finally:
        await database.dispose()

    assert str(journal_mode).lower() == "wal"
    assert foreign_keys == 1
    assert busy_timeout == 5_000
    assert synchronous == 1  # NORMAL
    assert temp_store == 2  # MEMORY


@pytest.mark.asyncio
async def test_reader_transaction_keeps_wal_snapshot(tmp_path: Path) -> None:
    database = create_database(tmp_path / "agent.db")

    try:
        async with database.engine.begin() as connection:
            await connection.execute(text("CREATE TABLE counters (value INTEGER NOT NULL)"))
            await connection.execute(text("INSERT INTO counters (value) VALUES (1)"))

        async with (
            database.engine.connect() as reader,
            database.engine.connect() as writer,
        ):
            reader_transaction = await reader.begin()
            try:
                first_value = (
                    await reader.execute(text("SELECT value FROM counters"))
                ).scalar_one()

                async with writer.begin():
                    await writer.execute(text("UPDATE counters SET value = 2"))

                second_value = (
                    await reader.execute(text("SELECT value FROM counters"))
                ).scalar_one()
            finally:
                await reader_transaction.rollback()
    finally:
        await database.dispose()

    assert first_value == 1
    assert second_value == 1


@pytest.mark.asyncio
async def test_foundation_datetime_is_normalized_to_utc(tmp_path: Path) -> None:
    database = create_database(tmp_path / "agent.db")
    local_datetime = datetime(2026, 7, 11, 12, 30, tzinfo=timezone(timedelta(hours=8)))

    try:
        async with database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with database.sessions.begin() as session:
            session.add(
                EventLogRow(
                    event_type="test.created",
                    aggregate_type="test",
                    aggregate_id="test-1",
                    payload={},
                    created_at=local_datetime,
                )
            )

        async with database.sessions() as session:
            stored_datetime = (await session.execute(select(EventLogRow.created_at))).scalar_one()
    finally:
        await database.dispose()

    assert stored_datetime == datetime(2026, 7, 11, 4, 30, tzinfo=UTC)


@pytest.mark.asyncio
async def test_foundation_datetime_rejects_naive_values(tmp_path: Path) -> None:
    database = create_database(tmp_path / "agent.db")

    try:
        async with database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with database.sessions() as session:
            session.add(
                EventLogRow(
                    event_type="test.created",
                    aggregate_type="test",
                    aggregate_id="test-1",
                    payload={},
                    created_at=datetime(2026, 7, 11, 4, 30),
                )
            )

            with pytest.raises(StatementError) as exc_info:
                await session.commit()
    finally:
        await database.dispose()

    assert isinstance(exc_info.value.orig, ValueError)
    assert "timezone-aware" in str(exc_info.value.orig)


def test_offline_migration_does_not_create_data_directory(tmp_path: Path) -> None:
    backend_root = Path(__file__).resolve().parents[2]
    data_root = tmp_path / "offline-data-root"
    environment = os.environ.copy()
    environment["AGENT_PLATFORM_DATA_ROOT"] = str(data_root)
    environment.pop("AGENT_PLATFORM_SESSION_TOKEN", None)

    result = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head", "--sql"],
        cwd=backend_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not data_root.exists()


def test_outbox_event_log_id_avoids_redundant_non_unique_index() -> None:
    event_log_id_columns = ("event_log_id",)
    outbox_table = Base.metadata.tables["outbox_events"]
    unique_constraint_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in outbox_table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    explicit_index_columns = {
        tuple(column.name for column in index.columns) for index in outbox_table.indexes
    }

    assert event_log_id_columns in unique_constraint_columns
    assert event_log_id_columns not in explicit_index_columns
