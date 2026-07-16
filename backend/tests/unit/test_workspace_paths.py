import ctypes
import os
from pathlib import Path

import pytest

from agent_platform.infrastructure.projects.paths import (
    UnsafeWorkspacePathError,
    create_managed_workspace_root,
    resolve_project_path,
    validate_direct_workspace_root,
)


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


def test_direct_workspace_root_is_resolved_and_keyed(tmp_path: Path) -> None:
    resolved, key = validate_direct_workspace_root(tmp_path)

    assert resolved == tmp_path.resolve(strict=True)
    assert key


def test_workspace_roots_accept_windows_short_path_alias(tmp_path: Path) -> None:
    target = tmp_path / "long workspace root for short path validation"
    target.mkdir()
    short_target = _windows_short_path(target)

    direct_root, direct_key = validate_direct_workspace_root(short_target)
    managed_root, managed_key = create_managed_workspace_root(short_target, "project_123")

    assert direct_root == target.resolve(strict=True)
    assert direct_key
    assert managed_root == (target / "workspaces" / "project_123").resolve(strict=True)
    assert managed_key


def test_direct_workspace_root_must_be_absolute(tmp_path: Path) -> None:
    with pytest.raises(UnsafeWorkspacePathError) as raised:
        validate_direct_workspace_root(Path(tmp_path.name))

    assert raised.value.code == "workspace.path_not_absolute"


def test_direct_workspace_root_must_exist(tmp_path: Path) -> None:
    with pytest.raises(UnsafeWorkspacePathError) as raised:
        validate_direct_workspace_root(tmp_path / "missing")

    assert raised.value.code == "workspace.path_not_found"


def test_direct_workspace_root_rejects_links(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("host cannot create directory links")

    with pytest.raises(UnsafeWorkspacePathError) as raised:
        validate_direct_workspace_root(linked)

    assert raised.value.code == "workspace.path_unsafe"


def test_project_relative_path_resolves_inside_workspace(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    module = source / "app.py"
    module.write_text("pass\n", encoding="utf-8")

    assert resolve_project_path(tmp_path, "src/app.py") == module.resolve(strict=True)
    assert resolve_project_path(tmp_path, "new/output.txt", must_exist=False) == (
        tmp_path / "new" / "output.txt"
    )


def test_project_relative_path_rejects_missing_and_parent_segments(tmp_path: Path) -> None:
    with pytest.raises(UnsafeWorkspacePathError) as missing:
        resolve_project_path(tmp_path, "missing.txt")
    assert missing.value.code == "workspace.child_not_found"

    with pytest.raises(ValueError, match="canonical project-relative"):
        resolve_project_path(tmp_path, "../outside.txt", must_exist=False)


def test_project_relative_path_rejects_link_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("host cannot create directory links")

    with pytest.raises(UnsafeWorkspacePathError) as raised:
        resolve_project_path(tmp_path, "linked/file.txt", must_exist=False)

    assert raised.value.code == "workspace.path_escape"


def test_managed_workspace_is_created_under_data_root(tmp_path: Path) -> None:
    root, key = create_managed_workspace_root(tmp_path, "project_123")

    assert root == (tmp_path / "workspaces" / "project_123").resolve(strict=True)
    assert key


def test_managed_workspace_rejects_reparse_parent(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-managed"
    outside.mkdir()
    workspaces = tmp_path / "workspaces"
    try:
        workspaces.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("host cannot create directory links")

    with pytest.raises(UnsafeWorkspacePathError) as raised:
        create_managed_workspace_root(tmp_path, "project_123")

    assert raised.value.code == "workspace.managed_root_unsafe"
