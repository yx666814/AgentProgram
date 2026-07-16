from __future__ import annotations

import os
import re
import stat
from pathlib import Path

from agent_platform.domain.contracts.scalars import require_project_relative_path
from agent_platform.domain.shared.errors import DomainError, ErrorCategory

_WINDOWS_REPARSE_POINT = 0x400
_PROJECT_ID = re.compile(r"project_[a-z0-9]+\Z")


class UnsafeWorkspacePathError(DomainError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(
            code=code,
            message=message,
            category=ErrorCategory.INVALID_INPUT,
        )


def _is_link_or_reparse(path: Path) -> bool:
    metadata = path.lstat()
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & _WINDOWS_REPARSE_POINT
    )


def canonical_workspace_key(path: Path) -> str:
    canonical = str(path)
    return canonical.casefold() if os.name == "nt" else canonical


def _resolve_directory_without_links(
    path: Path,
    *,
    code: str,
    message: str,
) -> Path:
    current = path.absolute()
    while True:
        metadata = current.lstat()
        if stat.S_ISLNK(metadata.st_mode) or bool(
            getattr(metadata, "st_file_attributes", 0) & _WINDOWS_REPARSE_POINT
        ):
            raise UnsafeWorkspacePathError(code, message)
        if not stat.S_ISDIR(metadata.st_mode):
            raise UnsafeWorkspacePathError(code, message)
        if current.parent == current:
            break
        current = current.parent
    return path.resolve(strict=True)


def validate_direct_workspace_root(path: Path) -> tuple[Path, str]:
    if not path.is_absolute():
        raise UnsafeWorkspacePathError(
            "workspace.path_not_absolute",
            "Workspace path must be absolute",
        )
    try:
        resolved = _resolve_directory_without_links(
            path,
            code="workspace.path_unsafe",
            message="Workspace path cannot contain links or reparse points",
        )
        with os.scandir(resolved) as entries:
            next(entries, None)
    except UnsafeWorkspacePathError:
        raise
    except (FileNotFoundError, NotADirectoryError):
        raise UnsafeWorkspacePathError(
            "workspace.path_not_found",
            "Workspace directory does not exist",
        ) from None
    except PermissionError:
        raise UnsafeWorkspacePathError(
            "workspace.path_unreadable",
            "Workspace directory is not readable",
        ) from None
    except OSError:
        raise UnsafeWorkspacePathError(
            "workspace.path_unavailable",
            "Workspace directory is unavailable",
        ) from None
    return resolved, canonical_workspace_key(resolved)


def create_managed_workspace_root(data_root: Path, project_id: str) -> tuple[Path, str]:
    if _PROJECT_ID.fullmatch(project_id) is None:
        raise ValueError("project id is invalid")
    if not data_root.is_absolute():
        raise UnsafeWorkspacePathError(
            "workspace.managed_root_unsafe",
            "Managed workspace data root must be absolute",
        )
    try:
        resolved_data_root = _resolve_directory_without_links(
            data_root,
            code="workspace.managed_root_unsafe",
            message="Managed workspace data root cannot contain links or reparse points",
        )
        workspaces_root = resolved_data_root / "workspaces"
        _create_or_validate_owned_directory(workspaces_root)
        project_root = workspaces_root / project_id
        _create_or_validate_owned_directory(project_root)
        resolved = project_root.resolve(strict=True)
    except UnsafeWorkspacePathError:
        raise
    except OSError:
        raise UnsafeWorkspacePathError(
            "workspace.managed_root_unavailable",
            "Managed workspace could not be prepared",
        ) from None
    if resolved.parent != workspaces_root:
        raise UnsafeWorkspacePathError(
            "workspace.managed_root_unsafe",
            "Managed workspace escapes the application data root",
        )
    return resolved, canonical_workspace_key(resolved)


def resolve_project_path(
    workspace_root: Path,
    relative_path: str,
    *,
    must_exist: bool = True,
) -> Path:
    root, _ = validate_direct_workspace_root(workspace_root)
    canonical_relative = require_project_relative_path(relative_path)
    candidate = root.joinpath(*canonical_relative.split("/"))
    current = root
    missing_component = False
    try:
        for part in canonical_relative.split("/"):
            current /= part
            exists = current.exists() or current.is_symlink()
            if not exists:
                missing_component = True
                continue
            if missing_component or _is_link_or_reparse(current):
                raise UnsafeWorkspacePathError(
                    "workspace.path_escape",
                    "Project path cannot cross links or reparse points",
                )
        if must_exist and missing_component:
            raise UnsafeWorkspacePathError(
                "workspace.child_not_found",
                "Project path does not exist",
            )
        resolved = candidate.resolve(strict=must_exist)
    except UnsafeWorkspacePathError:
        raise
    except (FileNotFoundError, NotADirectoryError):
        raise UnsafeWorkspacePathError(
            "workspace.child_not_found",
            "Project path does not exist",
        ) from None
    except OSError:
        raise UnsafeWorkspacePathError(
            "workspace.path_unavailable",
            "Project path is unavailable",
        ) from None
    if not resolved.is_relative_to(root):
        raise UnsafeWorkspacePathError(
            "workspace.path_escape",
            "Project path escapes the workspace root",
        )
    return resolved


def _create_or_validate_owned_directory(path: Path) -> None:
    if path.exists() or path.is_symlink():
        if _is_link_or_reparse(path) or not path.is_dir():
            raise UnsafeWorkspacePathError(
                "workspace.managed_root_unsafe",
                "Managed workspace directory is unsafe",
            )
        return
    path.mkdir(exist_ok=False)
