from __future__ import annotations

import ctypes
import os
from datetime import timedelta
from pathlib import Path

import pytest

from agent_platform.infrastructure.logging import files as log_files
from agent_platform.infrastructure.logging.files import (
    SafeRotatingFileHandler,
    UnsafeLogPathError,
)


def _handler(log_root: Path) -> SafeRotatingFileHandler:
    return SafeRotatingFileHandler(
        log_root,
        max_bytes=64 * 1024,
        retained_file_count=2,
        retention_age=timedelta(days=1),
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows short paths are platform-specific")
def test_log_root_accepts_windows_short_path_alias(tmp_path: Path) -> None:
    target = tmp_path / "long directory name for short path validation"
    target.mkdir()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_short_path = kernel32.GetShortPathNameW
    get_short_path.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
    get_short_path.restype = ctypes.c_uint32
    buffer = ctypes.create_unicode_buffer(32_768)
    length = get_short_path(str(target), buffer, len(buffer))
    if length == 0 or length >= len(buffer):
        pytest.skip("Windows short path aliases are unavailable")
    short_target = Path(buffer.value)
    if short_target == target:
        pytest.skip("8.3 short-name generation is disabled")

    with _handler(short_target / "logs") as handler:
        handler.write_line(b'{"event":"short-path"}\n')

    assert (target / "logs" / "backend.jsonl").read_bytes() == (b'{"event":"short-path"}\n')


def test_failed_handler_initialization_can_be_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    handler = SafeRotatingFileHandler.__new__(SafeRotatingFileHandler)

    def reject_log_root(_: Path) -> Path:
        raise UnsafeLogPathError("log root is unsafe")

    monkeypatch.setattr(log_files, "_validate_log_root", reject_log_root)
    with pytest.raises(UnsafeLogPathError, match="log root is unsafe"):
        handler.__init__(
            tmp_path / "logs",
            max_bytes=64 * 1024,
            retained_file_count=2,
            retention_age=timedelta(days=1),
        )

    handler.close()
