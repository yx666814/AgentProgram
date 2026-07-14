from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog

from agent_platform.infrastructure.database.backup import (
    BackupReason,
    create_verified_backup,
    prune_backup_root,
)
from agent_platform.infrastructure.database.integrity import (
    IntegrityCheckMode,
    WalCheckpointMode,
    checkpoint_database,
    require_database_integrity,
)
from agent_platform.infrastructure.logging.files import prune_stale_log_files

_LOGGER = structlog.get_logger(__name__)


async def _run_blocking_safely[T](operation: Callable[[], T]) -> T:
    worker = asyncio.create_task(asyncio.to_thread(operation))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                continue
        try:
            worker.result()
        except BaseException:
            pass
        raise


@dataclass(frozen=True, slots=True)
class DatabaseHealthSnapshot:
    last_integrity_check_at: datetime | None = None
    last_backup_at: datetime | None = None
    database_size_bytes: int = 0
    size_warning: bool = False
    checkpoint_busy: bool = False


class DatabaseMaintenance:
    def __init__(
        self,
        *,
        database_path: Path,
        backup_root: Path,
        log_root: Path,
        operation_timeout_seconds: float,
        maintenance_interval_seconds: float,
        integrity_interval_seconds: float,
        backup_interval_seconds: float,
        backup_retain_count: int,
        backup_retention_age: timedelta,
        log_retention_age: timedelta,
        max_entries_per_run: int,
        size_warning_bytes: int,
    ) -> None:
        self._database_path = database_path
        self._backup_root = backup_root
        self._log_root = log_root
        self._operation_timeout = operation_timeout_seconds
        self._maintenance_interval = maintenance_interval_seconds
        self._integrity_interval = integrity_interval_seconds
        self._backup_interval = backup_interval_seconds
        self._backup_retain_count = backup_retain_count
        self._backup_retention_age = backup_retention_age
        self._log_retention_age = log_retention_age
        self._max_entries = max_entries_per_run
        self._size_warning_bytes = size_warning_bytes
        now = time.monotonic()
        self._next_integrity = now + integrity_interval_seconds
        self._next_backup = now + backup_interval_seconds
        self._snapshot = DatabaseHealthSnapshot()
        self._run_lock = asyncio.Lock()

    @property
    def snapshot(self) -> DatabaseHealthSnapshot:
        return self._snapshot

    async def run_once(
        self,
        *,
        force_integrity: bool = False,
        force_backup: bool = False,
    ) -> None:
        async with self._run_lock:
            now_mono = time.monotonic()
            now_utc = datetime.now(UTC)
            checkpoint = await checkpoint_database(
                self._database_path,
                WalCheckpointMode.PASSIVE,
                self._operation_timeout,
            )
            size = self._database_path.stat().st_size if self._database_path.exists() else 0
            self._snapshot = replace(
                self._snapshot,
                database_size_bytes=size,
                size_warning=size >= self._size_warning_bytes,
                checkpoint_busy=checkpoint.busy != 0,
            )
            if self._snapshot.size_warning:
                _LOGGER.warning("database_size_warning", database_size_bytes=size)

            await _run_blocking_safely(
                lambda: prune_backup_root(
                    self._backup_root,
                    retain_count=self._backup_retain_count,
                    retention_age=self._backup_retention_age,
                    max_entries=self._max_entries,
                    now=now_utc,
                )
            )
            await _run_blocking_safely(
                lambda: prune_stale_log_files(
                    self._log_root,
                    retention_age=self._log_retention_age,
                    max_entries=self._max_entries,
                    now=now_utc,
                )
            )

            if force_integrity or now_mono >= self._next_integrity:
                await require_database_integrity(
                    self._database_path,
                    IntegrityCheckMode.FULL,
                    self._operation_timeout,
                )
                self._snapshot = replace(self._snapshot, last_integrity_check_at=now_utc)
                self._next_integrity = now_mono + self._integrity_interval

            if force_backup or now_mono >= self._next_backup:
                await _run_blocking_safely(
                    lambda: create_verified_backup(
                        self._database_path,
                        self._backup_root,
                        reason=BackupReason.SCHEDULED,
                        now=now_utc,
                    )
                )
                self._snapshot = replace(self._snapshot, last_backup_at=now_utc)
                self._next_backup = now_mono + self._backup_interval

    async def run_forever(self) -> None:
        while True:
            await asyncio.sleep(self._maintenance_interval)
            await self.run_once()

    async def final_checkpoint(self) -> None:
        result = await checkpoint_database(
            self._database_path,
            WalCheckpointMode.TRUNCATE,
            self._operation_timeout,
        )
        self._snapshot = replace(self._snapshot, checkpoint_busy=result.busy != 0)
