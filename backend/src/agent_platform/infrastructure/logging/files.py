from __future__ import annotations

import logging
import os
import re
import stat
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Final

_ROTATED_LOG_NAME: Final[re.Pattern[str]] = re.compile(r"backend\.jsonl\.[1-9][0-9]*\Z")
_WINDOWS_REPARSE_POINT: Final[int] = 0x400


class UnsafeLogPathError(RuntimeError):
    """Raised when an application-owned log path is unsafe."""


def _is_link_or_reparse(path: Path, metadata: os.stat_result | None = None) -> bool:
    current = metadata if metadata is not None else path.lstat()
    if stat.S_ISLNK(current.st_mode):
        return True
    attributes = getattr(current, "st_file_attributes", 0)
    return bool(attributes & _WINDOWS_REPARSE_POINT)


def _validate_log_root(log_root: Path) -> Path:
    if log_root.exists() or log_root.is_symlink():
        metadata = log_root.lstat()
        if _is_link_or_reparse(log_root, metadata) or not stat.S_ISDIR(metadata.st_mode):
            raise UnsafeLogPathError("log root is unsafe")
    else:
        log_root.mkdir(parents=True, exist_ok=False)
    resolved = log_root.resolve(strict=True)
    if resolved != log_root.absolute():
        raise UnsafeLogPathError("log root is unsafe")
    return resolved


def _validate_regular_candidate(path: Path, resolved_root: Path) -> os.stat_result:
    metadata = path.lstat()
    if _is_link_or_reparse(path, metadata) or not stat.S_ISREG(metadata.st_mode):
        raise UnsafeLogPathError("log file is unsafe")
    if path.resolve(strict=True).parent != resolved_root:
        raise UnsafeLogPathError("log file is unsafe")
    return metadata


def prune_stale_log_files(
    log_root: Path,
    *,
    retention_age: timedelta,
    now: datetime | None = None,
) -> None:
    resolved_root = _validate_log_root(log_root)
    cutoff = (now or datetime.now(UTC)) - retention_age
    for candidate in log_root.iterdir():
        if _ROTATED_LOG_NAME.fullmatch(candidate.name) is None:
            continue
        try:
            metadata = _validate_regular_candidate(candidate, resolved_root)
        except (FileNotFoundError, UnsafeLogPathError):
            continue
        if datetime.fromtimestamp(metadata.st_mtime, UTC) < cutoff:
            candidate.unlink()


class SafeRotatingFileHandler(logging.Handler):
    def __init__(
        self,
        log_root: Path,
        *,
        max_bytes: int,
        retained_file_count: int,
        retention_age: timedelta,
    ) -> None:
        super().__init__()
        self._log_root = log_root
        self._resolved_root = _validate_log_root(log_root)
        self._active_path = log_root / "backend.jsonl"
        self._max_bytes = max_bytes
        self._retained_file_count = retained_file_count
        self._retention_age = retention_age
        self._stream: BinaryIO | None = None
        self._lock = threading.RLock()

    @property
    def active_path(self) -> Path:
        return self._active_path

    def _open(self) -> BinaryIO:
        if self._active_path.exists() or self._active_path.is_symlink():
            _validate_regular_candidate(self._active_path, self._resolved_root)
        flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(self._active_path, flags, 0o600)
        try:
            opened = os.fstat(fd)
            if not stat.S_ISREG(opened.st_mode):
                raise UnsafeLogPathError("log file is unsafe")
            current = self._active_path.stat()
            if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
                raise UnsafeLogPathError("log file identity changed")
            return os.fdopen(fd, "ab", buffering=0)
        except BaseException:
            os.close(fd)
            raise

    def _ensure_stream(self) -> BinaryIO:
        if self._stream is None:
            self._stream = self._open()
        return self._stream

    def _validate_rollover_path(self, path: Path) -> None:
        if not (path.exists() or path.is_symlink()):
            return
        _validate_regular_candidate(path, self._resolved_root)

    def _rollover(self) -> None:
        if self._stream is not None:
            self._stream.flush()
            self._stream.close()
            self._stream = None

        self._validate_rollover_path(self._active_path)
        for index in range(self._retained_file_count, 0, -1):
            destination = self._log_root / f"backend.jsonl.{index}"
            self._validate_rollover_path(destination)
            if index == self._retained_file_count and destination.exists():
                destination.unlink()
            source = (
                self._active_path if index == 1 else self._log_root / f"backend.jsonl.{index - 1}"
            )
            self._validate_rollover_path(source)
            if source.exists():
                os.replace(source, destination)
        prune_stale_log_files(self._log_root, retention_age=self._retention_age)

    def write_line(self, line: bytes) -> None:
        with self._lock:
            stream = self._ensure_stream()
            current_size = os.fstat(stream.fileno()).st_size
            if current_size and current_size + len(line) > self._max_bytes:
                self._rollover()
                stream = self._ensure_stream()
            stream.write(line)
            stream.flush()

    def emit(self, record: logging.LogRecord) -> None:
        payload = record.msg
        if not isinstance(payload, bytes):
            raise TypeError("safe rotating handler requires bytes")
        self.write_line(payload)

    def close(self) -> None:
        with self._lock:
            if self._stream is not None:
                self._stream.flush()
                self._stream.close()
                self._stream = None
        super().close()

    def __enter__(self) -> SafeRotatingFileHandler:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        self.close()
