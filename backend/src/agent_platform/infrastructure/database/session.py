import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from sqlalchemy import event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import ConnectionPoolEntry


class _AioSQLiteDriverConnection(Protocol):
    _conn: sqlite3.Connection


class _AdaptedAioSQLiteConnection(Protocol):
    driver_connection: _AioSQLiteDriverConnection


@dataclass(frozen=True)
class Database:
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]

    async def dispose(self) -> None:
        await self.engine.dispose()


def _configure_sqlite_connection(
    dbapi_connection: DBAPIConnection,
    _connection_record: ConnectionPoolEntry,
) -> None:
    adapted_connection = cast(_AdaptedAioSQLiteConnection, dbapi_connection)
    raw_connection = adapted_connection.driver_connection._conn
    previous_autocommit = raw_connection.autocommit
    raw_connection.autocommit = True
    try:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA temp_store=MEMORY")
        finally:
            cursor.close()
    finally:
        raw_connection.autocommit = previous_autocommit


def create_database(path: Path) -> Database:
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{path.as_posix()}",
        connect_args={"autocommit": False},
    )
    event.listen(engine.sync_engine, "connect", _configure_sqlite_connection)
    sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return Database(engine=engine, sessions=sessions)
