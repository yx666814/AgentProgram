from __future__ import annotations

import hashlib
import json
import os
import stat
import threading
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from agent_platform.domain.projects import ProjectManifest, ProjectMetadata
from agent_platform.domain.shared.errors import DomainError, ErrorCategory
from agent_platform.infrastructure.projects.paths import validate_direct_workspace_root

_WINDOWS_REPARSE_POINT = 0x400
_METADATA_WRITE_LOCK = threading.Lock()


class ProjectMetadataError(DomainError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        category: ErrorCategory = ErrorCategory.CONFLICT,
    ) -> None:
        super().__init__(code=code, message=message, category=category)


class ProjectMetadataStore:
    def __init__(self, workspace_root: Path) -> None:
        self._workspace_root = workspace_root

    def initialize(self, metadata: ProjectMetadata) -> str:
        with _METADATA_WRITE_LOCK:
            agent_root = self._ensure_agent_root()
            path = agent_root / "project.json"
            if path.exists() or path.is_symlink():
                current = self._read_model(path, ProjectMetadata)
                if current != metadata:
                    raise ProjectMetadataError(
                        "project.metadata_conflict",
                        "Workspace is already registered to another project",
                    )
                return _sha256_bytes(_canonical_json_bytes(current))
            return self._atomic_write(path, _canonical_json_bytes(metadata))

    def read_metadata(self) -> ProjectMetadata:
        with _METADATA_WRITE_LOCK:
            path = self._ensure_agent_root() / "project.json"
            return self._read_model(path, ProjectMetadata)

    def write_manifest(
        self,
        manifest: ProjectManifest,
        *,
        expected_version: int | None,
    ) -> str:
        with _METADATA_WRITE_LOCK:
            agent_root = self._ensure_agent_root()
            metadata = self._read_model(agent_root / "project.json", ProjectMetadata)
            if metadata.project_id != manifest.project_id:
                raise ProjectMetadataError(
                    "project.manifest_project_mismatch",
                    "Manifest project does not match workspace metadata",
                )
            path = agent_root / "manifest.json"
            exists = path.exists() or path.is_symlink()
            if not exists:
                if expected_version is not None or manifest.manifest_version != 1:
                    raise ProjectMetadataError(
                        "project.manifest_version_conflict",
                        "Initial manifest version must be 1",
                    )
            else:
                current = self._read_model(path, ProjectManifest)
                if (
                    expected_version is None
                    or current.manifest_version != expected_version
                    or manifest.manifest_version != expected_version + 1
                ):
                    raise ProjectMetadataError(
                        "project.manifest_version_conflict",
                        "Manifest version has changed",
                    )
            return self._atomic_write(path, _canonical_json_bytes(manifest))

    def read_manifest(self) -> ProjectManifest:
        with _METADATA_WRITE_LOCK:
            path = self._ensure_agent_root() / "manifest.json"
            return self._read_model(path, ProjectManifest)

    def _ensure_agent_root(self) -> Path:
        root, _ = validate_direct_workspace_root(self._workspace_root)
        agent_root = root / ".agent"
        if agent_root.exists() or agent_root.is_symlink():
            metadata = agent_root.lstat()
            if _is_link_or_reparse(metadata) or not stat.S_ISDIR(metadata.st_mode):
                raise ProjectMetadataError(
                    "project.metadata_path_unsafe",
                    "Project metadata directory is unsafe",
                    category=ErrorCategory.INVALID_INPUT,
                )
        else:
            agent_root.mkdir(exist_ok=False)
        resolved = agent_root.resolve(strict=True)
        if resolved.parent != root:
            raise ProjectMetadataError(
                "project.metadata_path_unsafe",
                "Project metadata directory escapes the workspace",
                category=ErrorCategory.INVALID_INPUT,
            )
        return resolved

    def _read_model[ModelT: (ProjectMetadata, ProjectManifest)](
        self,
        path: Path,
        model_type: type[ModelT],
    ) -> ModelT:
        if not (path.exists() or path.is_symlink()):
            raise ProjectMetadataError(
                "project.metadata_not_found",
                "Project metadata does not exist",
                category=ErrorCategory.NOT_FOUND,
            )
        metadata = path.lstat()
        if _is_link_or_reparse(metadata) or not stat.S_ISREG(metadata.st_mode):
            raise ProjectMetadataError(
                "project.metadata_path_unsafe",
                "Project metadata file is unsafe",
                category=ErrorCategory.INVALID_INPUT,
            )
        try:
            return model_type.model_validate_json(path.read_bytes(), strict=True)
        except (OSError, ValidationError):
            raise ProjectMetadataError(
                "project.metadata_invalid",
                "Project metadata is invalid",
                category=ErrorCategory.INVALID_INPUT,
            ) from None

    def _atomic_write(self, path: Path, payload: bytes) -> str:
        if path.exists() or path.is_symlink():
            metadata = path.lstat()
            if _is_link_or_reparse(metadata) or not stat.S_ISREG(metadata.st_mode):
                raise ProjectMetadataError(
                    "project.metadata_path_unsafe",
                    "Project metadata file is unsafe",
                    category=ErrorCategory.INVALID_INPUT,
                )
        temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
            published = path.read_bytes()
        except OSError:
            raise ProjectMetadataError(
                "project.metadata_write_failed",
                "Project metadata could not be written",
                category=ErrorCategory.UNAVAILABLE,
            ) from None
        finally:
            temporary.unlink(missing_ok=True)
        expected_hash = _sha256_bytes(payload)
        if published != payload or _sha256_bytes(published) != expected_hash:
            raise ProjectMetadataError(
                "project.metadata_verification_failed",
                "Published project metadata failed verification",
                category=ErrorCategory.UNAVAILABLE,
            )
        return expected_hash


def _canonical_json_bytes(model: ProjectMetadata | ProjectManifest) -> bytes:
    document = model.model_dump(mode="json")
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _is_link_or_reparse(metadata: os.stat_result) -> bool:
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & _WINDOWS_REPARSE_POINT
    )
