import ctypes
import os
from pathlib import Path

import pytest

from agent_platform.domain.projects import CheckpointReason, ProjectManifest
from agent_platform.infrastructure.projects.checkpoints import CheckpointError, CheckpointStore


def _windows_short_path(path: Path) -> Path:
    if os.name != "nt":
        pytest.skip("Windows short paths are platform-specific")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_short_path = kernel32.GetShortPathNameW
    get_short_path.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
    get_short_path.restype = ctypes.c_uint32
    buffer = ctypes.create_unicode_buffer(32_768)
    length = get_short_path(str(path), buffer, len(buffer))
    if length == 0 or length >= len(buffer):
        pytest.skip("Windows short path aliases are unavailable")
    short_path = Path(buffer.value)
    if short_path == path:
        pytest.skip("8.3 short-name generation is disabled")
    return short_path


def _manifest(*, excluded_paths: tuple[str, ...] = ()) -> ProjectManifest:
    return ProjectManifest(
        schema_version=1,
        project_id="project_1",
        manifest_version=1,
        excluded_paths=excluded_paths,
    )


def test_checkpoint_storage_accepts_windows_short_path_alias(tmp_path: Path) -> None:
    target = tmp_path / "long checkpoint root for short path validation"
    target.mkdir()
    short_target = _windows_short_path(target)
    workspace = short_target / "workspace"
    workspace.mkdir()
    (workspace / "file.txt").write_text("content", encoding="utf-8")

    checkpoint = CheckpointStore(short_target / "snapshots").create(
        workspace,
        _manifest(),
        reason=CheckpointReason.MANUAL,
        checkpoint_id="checkpoint_short_path",
    )

    assert checkpoint.files[0].relative_path == "file.txt"
    assert (target / "snapshots" / "checkpoints" / "project_1").is_dir()


def test_checkpoint_is_content_addressed_deduplicated_and_loadable(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "src").mkdir()
    (workspace / ".agent").mkdir()
    (workspace / "excluded").mkdir()
    (workspace / "a.txt").write_bytes(b"same content\n")
    (workspace / "src" / "b.txt").write_bytes(b"same content\n")
    (workspace / ".agent" / "project.json").write_text("private", encoding="utf-8")
    (workspace / "excluded" / "secret.txt").write_text("secret", encoding="utf-8")
    store = CheckpointStore(tmp_path / "snapshots")

    checkpoint = store.create(
        workspace,
        _manifest(excluded_paths=("excluded",)),
        reason=CheckpointReason.MANUAL,
        checkpoint_id="checkpoint_one",
    )
    loaded = store.load("project_1", "checkpoint_one")
    blobs = list((tmp_path / "snapshots" / "blobs" / "sha256").glob("*/*"))

    assert loaded == checkpoint
    assert [file.relative_path for file in checkpoint.files] == ["a.txt", "src/b.txt"]
    assert len(blobs) == 1
    assert checkpoint.total_bytes == len(b"same content\n") * 2


def test_changed_content_creates_new_index_and_reuses_unchanged_blob(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    first_file = workspace / "first.txt"
    second_file = workspace / "second.txt"
    first_file.write_text("first", encoding="utf-8")
    second_file.write_text("stable", encoding="utf-8")
    store = CheckpointStore(tmp_path / "snapshots")
    first = store.create(
        workspace,
        _manifest(),
        reason=CheckpointReason.MANUAL,
        checkpoint_id="checkpoint_first",
    )

    first_file.write_text("changed", encoding="utf-8")
    second = store.create(
        workspace,
        _manifest(),
        reason=CheckpointReason.PRE_MUTATION,
        checkpoint_id="checkpoint_second",
    )

    assert first.content_hash != second.content_hash
    first_hashes = {file.content_hash for file in first.files}
    second_hashes = {file.content_hash for file in second.files}
    assert len(first_hashes & second_hashes) == 1


def test_checkpoint_verification_rejects_corrupt_blob(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "file.txt").write_text("original", encoding="utf-8")
    store = CheckpointStore(tmp_path / "snapshots")
    checkpoint = store.create(
        workspace,
        _manifest(),
        reason=CheckpointReason.MANUAL,
        checkpoint_id="checkpoint_corrupt",
    )
    digest = checkpoint.files[0].content_hash
    blob = tmp_path / "snapshots" / "blobs" / "sha256" / digest[:2] / digest
    blob.write_text("corrupt", encoding="utf-8")

    with pytest.raises(CheckpointError) as raised:
        store.verify(checkpoint)

    assert raised.value.code == "checkpoint.blob_corrupt"


def test_checkpoint_rejects_linked_project_paths(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = workspace / "linked"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("host cannot create directory links")

    with pytest.raises(CheckpointError) as raised:
        CheckpointStore(tmp_path / "snapshots").create(
            workspace,
            _manifest(),
            reason=CheckpointReason.MANUAL,
        )

    assert raised.value.code == "checkpoint.path_unsafe"


def test_restore_creates_protection_checkpoint_and_never_deletes_extra_files(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tracked = workspace / "tracked.txt"
    tracked.write_text("original", encoding="utf-8")
    store = CheckpointStore(tmp_path / "snapshots")
    target = store.create(
        workspace,
        _manifest(),
        reason=CheckpointReason.MANUAL,
        checkpoint_id="checkpoint_target",
    )
    tracked.write_text("user change", encoding="utf-8")
    extra = workspace / "extra-user-file.txt"
    extra.write_text("keep me", encoding="utf-8")

    result = store.restore(workspace, _manifest(), target)
    protection = store.load("project_1", result.protection_checkpoint_id)

    assert tracked.read_text(encoding="utf-8") == "original"
    assert extra.read_text(encoding="utf-8") == "keep me"
    assert result.restored_checkpoint_id == target.id
    assert {file.relative_path for file in protection.files} == {
        "extra-user-file.txt",
        "tracked.txt",
    }


def test_restore_failure_reports_protection_checkpoint(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tracked = workspace / "tracked.txt"
    tracked.write_text("original", encoding="utf-8")
    store = CheckpointStore(tmp_path / "snapshots")
    target = store.create(
        workspace,
        _manifest(),
        reason=CheckpointReason.MANUAL,
        checkpoint_id="checkpoint_target",
    )
    tracked.write_text("user change", encoding="utf-8")
    digest = target.files[0].content_hash
    blob = tmp_path / "snapshots" / "blobs" / "sha256" / digest[:2] / digest
    blob.write_text("corrupt", encoding="utf-8")

    with pytest.raises(CheckpointError) as raised:
        store.restore(workspace, _manifest(), target)

    protection_id = raised.value.details["protection_checkpoint_id"]
    assert isinstance(protection_id, str)
    assert store.load("project_1", protection_id).reason is CheckpointReason.PRE_RESTORE
    assert tracked.read_text(encoding="utf-8") == "user change"
