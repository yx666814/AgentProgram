from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from uuid import uuid4

from agent_platform.domain.shared.errors import DomainError, ErrorCategory
from agent_platform.domain.tooling import FileToolResult
from agent_platform.infrastructure.projects.paths import resolve_project_path

_WINDOWS_REPARSE_POINT = 0x400


class AtomicFileTools:
    def __init__(self, *, max_file_bytes: int) -> None:
        self._max_file_bytes = max_file_bytes

    def read(self, workspace_root: Path, relative_path: str) -> tuple[FileToolResult, bytes]:
        path = resolve_project_path(workspace_root, relative_path)
        metadata = self._require_regular_file(path)
        if metadata.st_size > self._max_file_bytes:
            raise _invalid("tool.file_too_large", "Project file exceeds tool limit")
        try:
            payload = path.read_bytes()
        except OSError:
            raise _unavailable("tool.file_read_failed", "Project file could not be read") from None
        if len(payload) != metadata.st_size:
            raise _conflict("tool.file_changed", "Project file changed during read")
        return _file_result(relative_path, payload), payload

    def write(
        self,
        workspace_root: Path,
        relative_path: str,
        payload: bytes,
        *,
        expected_hash: str | None,
    ) -> FileToolResult:
        if len(payload) > self._max_file_bytes:
            raise _invalid("tool.file_too_large", "Project file exceeds tool limit")
        path = resolve_project_path(workspace_root, relative_path, must_exist=False)
        self._ensure_parent(workspace_root, path.parent)
        if path.exists() or path.is_symlink():
            current = self._require_regular_file(path)
            if current.st_size > self._max_file_bytes:
                raise _invalid("tool.file_too_large", "Project file exceeds tool limit")
            current_hash = _sha256(path.read_bytes())
            if expected_hash is None or current_hash != expected_hash:
                raise _conflict("tool.file_version_conflict", "Project file version has changed")
        elif expected_hash is not None:
            raise _conflict("tool.file_version_conflict", "Project file does not exist")
        temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
            published = path.read_bytes()
        except OSError:
            raise _unavailable(
                "tool.file_write_failed", "Project file could not be written"
            ) from None
        finally:
            temporary.unlink(missing_ok=True)
        if published != payload:
            raise _unavailable("tool.file_verification_failed", "Project file verification failed")
        return _file_result(relative_path, published)

    def create_directory(self, workspace_root: Path, relative_path: str) -> FileToolResult:
        path = resolve_project_path(workspace_root, relative_path, must_exist=False)
        self._ensure_parent(workspace_root, path.parent)
        if path.exists() or path.is_symlink():
            metadata = path.lstat()
            if _is_link_or_reparse(metadata) or not stat.S_ISDIR(metadata.st_mode):
                raise _invalid("tool.path_unsafe", "Project path is unsafe")
        else:
            try:
                path.mkdir(exist_ok=False)
            except OSError:
                raise _unavailable(
                    "tool.directory_create_failed", "Project directory could not be created"
                ) from None
        return FileToolResult(relative_path=relative_path, content_hash=_sha256(b""), byte_size=0)

    def delete(
        self,
        workspace_root: Path,
        relative_path: str,
        *,
        expected_hash: str,
    ) -> FileToolResult:
        path = resolve_project_path(workspace_root, relative_path)
        metadata = self._require_regular_file(path)
        if metadata.st_size > self._max_file_bytes:
            raise _invalid("tool.file_too_large", "Project file exceeds tool limit")
        payload = path.read_bytes()
        result = _file_result(relative_path, payload)
        if result.content_hash != expected_hash:
            raise _conflict("tool.file_version_conflict", "Project file version has changed")
        try:
            path.unlink()
        except OSError:
            raise _unavailable(
                "tool.file_delete_failed", "Project file could not be deleted"
            ) from None
        return result

    def _ensure_parent(self, workspace_root: Path, parent: Path) -> None:
        root = workspace_root.resolve(strict=True)
        relative_parts = parent.relative_to(root).parts
        current = root
        for part in relative_parts:
            current /= part
            if current.exists() or current.is_symlink():
                metadata = current.lstat()
                if _is_link_or_reparse(metadata) or not stat.S_ISDIR(metadata.st_mode):
                    raise _invalid("tool.path_unsafe", "Project path is unsafe")
            else:
                try:
                    current.mkdir(exist_ok=False)
                except OSError:
                    raise _unavailable(
                        "tool.directory_create_failed", "Project directory could not be created"
                    ) from None

    @staticmethod
    def _require_regular_file(path: Path) -> os.stat_result:
        try:
            metadata = path.lstat()
        except OSError:
            raise _invalid("tool.file_not_found", "Project file was not found") from None
        if _is_link_or_reparse(metadata) or not stat.S_ISREG(metadata.st_mode):
            raise _invalid("tool.path_unsafe", "Project path is unsafe")
        return metadata


def _file_result(relative_path: str, payload: bytes) -> FileToolResult:
    return FileToolResult(
        relative_path=relative_path,
        content_hash=_sha256(payload),
        byte_size=len(payload),
    )


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _is_link_or_reparse(metadata: os.stat_result) -> bool:
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & _WINDOWS_REPARSE_POINT
    )


def _invalid(code: str, message: str) -> DomainError:
    return DomainError(code=code, message=message, category=ErrorCategory.INVALID_INPUT)


def _conflict(code: str, message: str) -> DomainError:
    return DomainError(code=code, message=message, category=ErrorCategory.CONFLICT)


def _unavailable(code: str, message: str) -> DomainError:
    return DomainError(code=code, message=message, category=ErrorCategory.UNAVAILABLE)
