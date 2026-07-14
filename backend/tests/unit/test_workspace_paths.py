from pathlib import Path

import pytest

from agent_platform.infrastructure.projects.paths import (
    UnsafeWorkspacePathError,
    validate_direct_workspace_root,
)


def test_direct_workspace_root_is_resolved_and_keyed(tmp_path: Path) -> None:
    resolved, key = validate_direct_workspace_root(tmp_path)

    assert resolved == tmp_path.resolve(strict=True)
    assert key


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
