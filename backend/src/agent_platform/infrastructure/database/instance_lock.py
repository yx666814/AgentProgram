from __future__ import annotations

import importlib
import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from agent_platform import __version__
from agent_platform.domain.shared.errors import DomainError, ErrorCategory

_WINDOWS_REPARSE_POINT = 0x400


class InstanceLockUnavailableError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            code="backend.instance_unavailable",
            message="Backend data root is already in use",
            retryable=True,
            category=ErrorCategory.UNAVAILABLE,
        )


def _is_link_or_reparse(path: Path) -> bool:
    metadata = path.lstat()
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & _WINDOWS_REPARSE_POINT
    )


def _ensure_safe_runtime_root(runtime_root: Path) -> None:
    if runtime_root.exists() or runtime_root.is_symlink():
        if _is_link_or_reparse(runtime_root) or not runtime_root.is_dir():
            raise OSError("runtime root is unsafe")
    else:
        runtime_root.mkdir(parents=True, exist_ok=False)


class ApplicationInstanceLock:
    def __init__(self, path: Path, handle: BinaryIO) -> None:
        self.path = path
        self._handle: BinaryIO | None = handle

    @classmethod
    def acquire(cls, runtime_root: Path) -> ApplicationInstanceLock:
        _ensure_safe_runtime_root(runtime_root)
        path = runtime_root / "backend.lock"
        if path.exists() or path.is_symlink():
            if _is_link_or_reparse(path) or not path.is_file():
                raise OSError("instance lock path is unsafe")
        try:
            handle = path.open("x+b", buffering=0)
        except FileExistsError:
            handle = path.open("r+b", buffering=0)
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
                os.fsync(handle.fileno())
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError:
                    raise InstanceLockUnavailableError from None
            else:
                fcntl = importlib.import_module("fcntl")

                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    raise InstanceLockUnavailableError from None
            metadata = json.dumps(
                {
                    "pid": os.getpid(),
                    "version": __version__,
                    "acquired_at": datetime.now(UTC).isoformat(),
                },
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            handle.seek(0)
            handle.write(metadata)
            handle.truncate()
            handle.flush()
            os.fsync(handle.fileno())
            return cls(path, handle)
        except BaseException:
            handle.close()
            raise

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        self._handle = None
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl = importlib.import_module("fcntl")

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    def __enter__(self) -> ApplicationInstanceLock:
        return self

    def __exit__(self, *_: object) -> None:
        self.release()
