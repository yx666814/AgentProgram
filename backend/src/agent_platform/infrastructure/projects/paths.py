from __future__ import annotations

import os
import stat
from pathlib import Path

from agent_platform.domain.shared.errors import DomainError, ErrorCategory

_WINDOWS_REPARSE_POINT = 0x400


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


def validate_direct_workspace_root(path: Path) -> tuple[Path, str]:
    if not path.is_absolute():
        raise UnsafeWorkspacePathError(
            "workspace.path_not_absolute",
            "Workspace path must be absolute",
        )
    try:
        if _is_link_or_reparse(path) or not path.is_dir():
            raise UnsafeWorkspacePathError(
                "workspace.path_unsafe",
                "Workspace path must be a regular directory",
            )
        absolute = path.absolute()
        resolved = path.resolve(strict=True)
        if resolved != absolute:
            raise UnsafeWorkspacePathError(
                "workspace.path_unsafe",
                "Workspace path cannot contain links or reparse points",
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
