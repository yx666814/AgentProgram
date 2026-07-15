import json
from pathlib import Path

import pytest

from agent_platform.infrastructure.database.instance_lock import (
    ApplicationInstanceLock,
    InstanceLockUnavailableError,
)


def test_instance_lock_is_exclusive_and_reacquirable(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    first = ApplicationInstanceLock.acquire(runtime_root)
    try:
        with pytest.raises(InstanceLockUnavailableError):
            ApplicationInstanceLock.acquire(runtime_root)
    finally:
        first.release()

    metadata = json.loads((runtime_root / "backend.lock").read_text(encoding="utf-8"))
    assert set(metadata) == {"pid", "version", "acquired_at"}

    second = ApplicationInstanceLock.acquire(runtime_root)
    second.release()
    second.release()


def test_instance_lock_rejects_linked_runtime_root(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("host cannot create directory symlinks")

    with pytest.raises(OSError, match="unsafe"):
        ApplicationInstanceLock.acquire(linked)
