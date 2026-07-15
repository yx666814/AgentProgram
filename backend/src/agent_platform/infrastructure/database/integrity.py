from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from agent_platform.domain.shared.errors import DomainError, ErrorCategory


class IntegrityCheckMode(StrEnum):
    QUICK = "quick_check"
    FULL = "integrity_check"


class WalCheckpointMode(StrEnum):
    PASSIVE = "PASSIVE"
    TRUNCATE = "TRUNCATE"


@dataclass(frozen=True, slots=True)
class IntegrityCheckResult:
    mode: IntegrityCheckMode
    ok: bool


@dataclass(frozen=True, slots=True)
class WalCheckpointResult:
    busy: int
    log_frames: int
    checkpointed_frames: int


@dataclass(frozen=True, slots=True)
class _OperationControl:
    deadline: float
    cancelled: threading.Event

    def should_abort(self) -> bool:
        return self.cancelled.is_set() or time.monotonic() >= self.deadline


class DatabaseOperationTimeout(RuntimeError):
    pass


class DatabaseIntegrityError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            code="database.integrity_failed",
            message="Database integrity validation failed",
            retryable=False,
            category=ErrorCategory.UNAVAILABLE,
        )


def _raise_if_aborted(control: _OperationControl) -> None:
    if control.should_abort():
        raise DatabaseOperationTimeout("database operation timed out")


async def _join_worker[T](worker: asyncio.Task[T]) -> T:
    cancellation_count = 0
    while True:
        try:
            result = await asyncio.shield(worker)
            break
        except asyncio.CancelledError:
            cancellation_count += 1
            continue
    if cancellation_count:
        current = asyncio.current_task()
        if current is not None:
            for _ in range(cancellation_count):
                current.cancel()
        raise asyncio.CancelledError
    return result


async def run_controlled_database_operation[T](
    operation: Callable[[_OperationControl], T],
    timeout_seconds: float,
) -> T:
    if timeout_seconds <= 0:
        raise ValueError("database operation timeout must be positive")
    control = _OperationControl(
        deadline=time.monotonic() + timeout_seconds,
        cancelled=threading.Event(),
    )
    worker = asyncio.create_task(asyncio.to_thread(operation, control))
    try:
        return await asyncio.wait_for(asyncio.shield(worker), timeout=timeout_seconds + 0.25)
    except TimeoutError:
        control.cancelled.set()
        try:
            await _join_worker(worker)
        except (DatabaseOperationTimeout, asyncio.CancelledError):
            pass
        raise DatabaseOperationTimeout("database operation timed out") from None
    except asyncio.CancelledError:
        control.cancelled.set()
        try:
            await _join_worker(worker)
        except (DatabaseOperationTimeout, asyncio.CancelledError):
            pass
        raise


def _open_connection(path: Path, timeout_seconds: float) -> sqlite3.Connection:
    return sqlite3.connect(path, timeout=timeout_seconds, isolation_level=None)


async def check_database_integrity(
    path: Path,
    mode: IntegrityCheckMode,
    timeout_seconds: float,
) -> IntegrityCheckResult:
    def operation(control: _OperationControl) -> IntegrityCheckResult:
        _raise_if_aborted(control)
        with closing(_open_connection(path, timeout_seconds)) as connection:
            connection.set_progress_handler(lambda: 1 if control.should_abort() else 0, 1000)
            try:
                rows = list(connection.execute(f"PRAGMA {mode.value}"))
            except sqlite3.DatabaseError:
                _raise_if_aborted(control)
                return IntegrityCheckResult(mode=mode, ok=False)
        _raise_if_aborted(control)
        return IntegrityCheckResult(mode=mode, ok=rows == [("ok",)])

    return await run_controlled_database_operation(operation, timeout_seconds)


async def require_database_integrity(
    path: Path,
    mode: IntegrityCheckMode,
    timeout_seconds: float,
) -> None:
    result = await check_database_integrity(path, mode, timeout_seconds)
    if not result.ok:
        raise DatabaseIntegrityError


async def checkpoint_database(
    path: Path,
    mode: WalCheckpointMode,
    timeout_seconds: float,
) -> WalCheckpointResult:
    def operation(control: _OperationControl) -> WalCheckpointResult:
        _raise_if_aborted(control)
        with closing(_open_connection(path, timeout_seconds)) as connection:
            row = connection.execute(f"PRAGMA wal_checkpoint({mode.value})").fetchone()
        _raise_if_aborted(control)
        if row is None or len(row) != 3:
            raise RuntimeError("database checkpoint returned an invalid result")
        return WalCheckpointResult(
            busy=int(row[0]),
            log_frames=int(row[1]),
            checkpointed_frames=int(row[2]),
        )

    return await run_controlled_database_operation(operation, timeout_seconds)
