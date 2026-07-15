from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from agent_platform.domain.projects import (
    CheckpointFile,
    CheckpointReason,
    CheckpointRestoreResult,
    ProjectCheckpoint,
    ProjectManifest,
)
from agent_platform.domain.shared.errors import DomainError, ErrorCategory
from agent_platform.domain.shared.ids import new_id
from agent_platform.infrastructure.projects.paths import (
    resolve_project_path,
    validate_direct_workspace_root,
)

_WINDOWS_REPARSE_POINT = 0x400
_SAFE_ID = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+\Z")
_CHECKPOINT_LOCK = threading.RLock()


class CheckpointError(DomainError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, object] | None = None,
        category: ErrorCategory = ErrorCategory.CONFLICT,
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            details=details or {},
            category=category,
        )


class CheckpointStore:
    def __init__(
        self,
        snapshot_root: Path,
        *,
        max_files: int = 100_000,
        max_file_bytes: int = 1024 * 1024 * 1024,
        max_total_bytes: int = 10 * 1024 * 1024 * 1024,
    ) -> None:
        if min(max_files, max_file_bytes, max_total_bytes) <= 0:
            raise ValueError("checkpoint limits must be positive")
        self._snapshot_root = snapshot_root
        self._max_files = max_files
        self._max_file_bytes = max_file_bytes
        self._max_total_bytes = max_total_bytes

    def create(
        self,
        workspace_root: Path,
        manifest: ProjectManifest,
        *,
        reason: CheckpointReason,
        checkpoint_id: str | None = None,
        created_at: datetime | None = None,
    ) -> ProjectCheckpoint:
        with _CHECKPOINT_LOCK:
            root, _ = validate_direct_workspace_root(workspace_root)
            snapshot_root = self._ensure_snapshot_layout()
            files = self._enumerate_project_files(root, manifest.excluded_paths)
            captured: list[CheckpointFile] = []
            total_bytes = 0
            for relative_path, source in files:
                checkpoint_file = self._capture_file(snapshot_root, source, relative_path)
                total_bytes += checkpoint_file.byte_size
                if total_bytes > self._max_total_bytes:
                    raise CheckpointError(
                        "checkpoint.total_size_exceeded",
                        "Project exceeds the checkpoint size limit",
                    )
                captured.append(checkpoint_file)
            frozen_files = tuple(captured)
            checkpoint = ProjectCheckpoint(
                schema_version=1,
                id=checkpoint_id or new_id("checkpoint"),
                project_id=manifest.project_id,
                manifest_version=manifest.manifest_version,
                reason=reason,
                content_hash=_file_index_hash(frozen_files),
                files=frozen_files,
                total_bytes=total_bytes,
                created_at=created_at or datetime.now(UTC),
            )
            self._publish_checkpoint_manifest(snapshot_root, checkpoint)
            self._verify(snapshot_root, checkpoint)
            return checkpoint

    def load(self, project_id: str, checkpoint_id: str) -> ProjectCheckpoint:
        with _CHECKPOINT_LOCK:
            snapshot_root = self._ensure_snapshot_layout()
            path = self._checkpoint_path(snapshot_root, project_id, checkpoint_id)
            _require_regular_file(path, code="checkpoint.manifest_unsafe")
            try:
                checkpoint = ProjectCheckpoint.model_validate_json(
                    path.read_bytes(),
                    strict=True,
                )
            except (OSError, ValidationError):
                raise CheckpointError(
                    "checkpoint.manifest_invalid",
                    "Checkpoint manifest is invalid",
                    category=ErrorCategory.INVALID_INPUT,
                ) from None
            if checkpoint.project_id != project_id or checkpoint.id != checkpoint_id:
                raise CheckpointError(
                    "checkpoint.manifest_invalid",
                    "Checkpoint identity does not match its path",
                    category=ErrorCategory.INVALID_INPUT,
                )
            self._verify(snapshot_root, checkpoint)
            return checkpoint

    def verify(self, checkpoint: ProjectCheckpoint) -> None:
        with _CHECKPOINT_LOCK:
            snapshot_root = self._ensure_snapshot_layout()
            self._verify(snapshot_root, checkpoint)

    def restore(
        self,
        workspace_root: Path,
        manifest: ProjectManifest,
        checkpoint: ProjectCheckpoint,
    ) -> CheckpointRestoreResult:
        if checkpoint.project_id != manifest.project_id:
            raise CheckpointError(
                "checkpoint.project_mismatch",
                "Checkpoint belongs to another project",
                category=ErrorCategory.INVALID_INPUT,
            )
        protection = self.create(
            workspace_root,
            manifest,
            reason=CheckpointReason.PRE_RESTORE,
        )
        return self.restore_prepared(workspace_root, checkpoint, protection)

    def restore_prepared(
        self,
        workspace_root: Path,
        checkpoint: ProjectCheckpoint,
        protection: ProjectCheckpoint,
    ) -> CheckpointRestoreResult:
        if checkpoint.project_id != protection.project_id:
            raise CheckpointError(
                "checkpoint.project_mismatch",
                "Protection checkpoint belongs to another project",
                category=ErrorCategory.INVALID_INPUT,
            )
        with _CHECKPOINT_LOCK:
            try:
                snapshot_root = self._ensure_snapshot_layout()
                self._verify(snapshot_root, checkpoint)
                self._verify(snapshot_root, protection)
                root, _ = validate_direct_workspace_root(workspace_root)
                self._require_workspace_matches_protection(root, checkpoint, protection)
                for checkpoint_file in checkpoint.files:
                    self._restore_file(snapshot_root, root, checkpoint_file)
            except BaseException as error:
                if isinstance(error, (KeyboardInterrupt, SystemExit)):
                    raise
                raise CheckpointError(
                    "checkpoint.restore_incomplete",
                    "Checkpoint restore did not complete",
                    details={"protection_checkpoint_id": protection.id},
                    category=ErrorCategory.UNAVAILABLE,
                ) from None
        return CheckpointRestoreResult(
            schema_version=1,
            restored_checkpoint_id=checkpoint.id,
            protection_checkpoint_id=protection.id,
            restored_file_count=len(checkpoint.files),
        )

    def materialize_empty_workspace(
        self,
        workspace_root: Path,
        checkpoint: ProjectCheckpoint,
    ) -> None:
        with _CHECKPOINT_LOCK:
            snapshot_root = self._ensure_snapshot_layout()
            self._verify(snapshot_root, checkpoint)
            root, _ = validate_direct_workspace_root(workspace_root)
            with os.scandir(root) as entries:
                if next(entries, None) is not None:
                    raise CheckpointError(
                        "checkpoint.workspace_not_empty",
                        "Managed workspace is not empty",
                    )
            for checkpoint_file in checkpoint.files:
                self._restore_file(snapshot_root, root, checkpoint_file)

    def restore_file(
        self,
        workspace_root: Path,
        checkpoint_file: CheckpointFile,
    ) -> None:
        with _CHECKPOINT_LOCK:
            snapshot_root = self._ensure_snapshot_layout()
            root, _ = validate_direct_workspace_root(workspace_root)
            self._restore_file(snapshot_root, root, checkpoint_file)

    def delete_file(self, workspace_root: Path, relative_path: str) -> None:
        with _CHECKPOINT_LOCK:
            target = resolve_project_path(workspace_root, relative_path, must_exist=False)
            if not (target.exists() or target.is_symlink()):
                return
            _require_regular_file(target, code="checkpoint.restore_path_unsafe")
            try:
                target.unlink()
            except OSError:
                raise CheckpointError(
                    "checkpoint.delete_failed",
                    "Conflict file could not be deleted",
                    category=ErrorCategory.UNAVAILABLE,
                ) from None

    def file_hash(self, workspace_root: Path, relative_path: str) -> str | None:
        with _CHECKPOINT_LOCK:
            target = resolve_project_path(workspace_root, relative_path, must_exist=False)
            if not (target.exists() or target.is_symlink()):
                return None
            metadata = _require_regular_file(target, code="checkpoint.restore_path_unsafe")
            return _hash_regular_file(target, metadata.st_size)

    def _ensure_snapshot_layout(self) -> Path:
        root = _create_or_validate_directory(self._snapshot_root, parents=True)
        _create_or_validate_directory(root / "blobs")
        _create_or_validate_directory(root / "blobs" / "sha256")
        _create_or_validate_directory(root / "checkpoints")
        _create_or_validate_directory(root / "temp")
        return root

    def _enumerate_project_files(
        self,
        workspace_root: Path,
        excluded_paths: tuple[str, ...],
    ) -> tuple[tuple[str, Path], ...]:
        files: list[tuple[str, Path]] = []

        def visit(directory: Path, prefix: str) -> None:
            try:
                entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
            except OSError:
                raise CheckpointError(
                    "checkpoint.workspace_unreadable",
                    "Project files could not be enumerated",
                    category=ErrorCategory.UNAVAILABLE,
                ) from None
            for entry in entries:
                relative_path = f"{prefix}/{entry.name}" if prefix else entry.name
                canonical_path = relative_path.replace(os.sep, "/")
                if _is_excluded(canonical_path, excluded_paths):
                    continue
                path = Path(entry.path)
                try:
                    metadata = path.lstat()
                except OSError:
                    raise CheckpointError(
                        "checkpoint.workspace_changed",
                        "Project changed while creating a checkpoint",
                    ) from None
                if _is_link_or_reparse(metadata):
                    raise CheckpointError(
                        "checkpoint.path_unsafe",
                        "Project contains a linked or reparse path",
                        details={"relative_path": canonical_path},
                        category=ErrorCategory.INVALID_INPUT,
                    )
                if stat.S_ISDIR(metadata.st_mode):
                    visit(path, canonical_path)
                elif stat.S_ISREG(metadata.st_mode):
                    files.append((canonical_path, path))
                    if len(files) > self._max_files:
                        raise CheckpointError(
                            "checkpoint.file_count_exceeded",
                            "Project exceeds the checkpoint file limit",
                        )
                else:
                    raise CheckpointError(
                        "checkpoint.path_unsafe",
                        "Project contains an unsupported file type",
                        details={"relative_path": canonical_path},
                        category=ErrorCategory.INVALID_INPUT,
                    )

        visit(workspace_root, "")
        return tuple(files)

    def _capture_file(
        self,
        snapshot_root: Path,
        source: Path,
        relative_path: str,
    ) -> CheckpointFile:
        before = source.lstat()
        if _is_link_or_reparse(before) or not stat.S_ISREG(before.st_mode):
            raise CheckpointError(
                "checkpoint.path_unsafe",
                "Project file is unsafe",
                details={"relative_path": relative_path},
            )
        if before.st_size > self._max_file_bytes:
            raise CheckpointError(
                "checkpoint.file_size_exceeded",
                "Project file exceeds the checkpoint size limit",
                details={"relative_path": relative_path},
            )
        temporary = snapshot_root / "temp" / f"blob-{uuid4().hex}.tmp"
        digest = hashlib.sha256()
        byte_size = 0
        try:
            with source.open("rb") as input_file, temporary.open("xb") as output_file:
                opened = os.fstat(input_file.fileno())
                if not _same_file_version(before, opened):
                    raise CheckpointError(
                        "checkpoint.workspace_changed",
                        "Project changed while creating a checkpoint",
                    )
                while chunk := input_file.read(1024 * 1024):
                    byte_size += len(chunk)
                    if byte_size > self._max_file_bytes:
                        raise CheckpointError(
                            "checkpoint.file_size_exceeded",
                            "Project file exceeds the checkpoint size limit",
                            details={"relative_path": relative_path},
                        )
                    digest.update(chunk)
                    output_file.write(chunk)
                after = os.fstat(input_file.fileno())
                if not _same_file_version(before, after) or byte_size != after.st_size:
                    raise CheckpointError(
                        "checkpoint.workspace_changed",
                        "Project changed while creating a checkpoint",
                    )
                output_file.flush()
                os.fsync(output_file.fileno())
            content_hash = digest.hexdigest()
            blob = self._blob_path(snapshot_root, content_hash)
            self._publish_blob(temporary, blob, content_hash, byte_size)
        finally:
            temporary.unlink(missing_ok=True)
        return CheckpointFile(
            relative_path=relative_path,
            content_hash=content_hash,
            byte_size=byte_size,
        )

    def _publish_blob(
        self,
        temporary: Path,
        blob: Path,
        content_hash: str,
        byte_size: int,
    ) -> None:
        _create_or_validate_directory(blob.parent)
        if blob.exists() or blob.is_symlink():
            _verify_file(blob, content_hash, byte_size, code="checkpoint.blob_corrupt")
            return
        try:
            os.replace(temporary, blob)
        except OSError:
            raise CheckpointError(
                "checkpoint.blob_write_failed",
                "Checkpoint blob could not be published",
                category=ErrorCategory.UNAVAILABLE,
            ) from None
        _verify_file(blob, content_hash, byte_size, code="checkpoint.blob_corrupt")

    def _publish_checkpoint_manifest(
        self,
        snapshot_root: Path,
        checkpoint: ProjectCheckpoint,
    ) -> None:
        path = self._checkpoint_path(snapshot_root, checkpoint.project_id, checkpoint.id)
        _create_or_validate_directory(path.parent)
        if path.exists() or path.is_symlink():
            raise CheckpointError(
                "checkpoint.already_exists",
                "Checkpoint already exists",
            )
        payload = _canonical_json(checkpoint)
        temporary = snapshot_root / "temp" / f"checkpoint-{uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
            if path.read_bytes() != payload:
                raise CheckpointError(
                    "checkpoint.manifest_write_failed",
                    "Checkpoint manifest failed verification",
                )
        except CheckpointError:
            raise
        except OSError:
            raise CheckpointError(
                "checkpoint.manifest_write_failed",
                "Checkpoint manifest could not be published",
                category=ErrorCategory.UNAVAILABLE,
            ) from None
        finally:
            temporary.unlink(missing_ok=True)

    def _verify(self, snapshot_root: Path, checkpoint: ProjectCheckpoint) -> None:
        if checkpoint.content_hash != _file_index_hash(checkpoint.files):
            raise CheckpointError(
                "checkpoint.index_hash_mismatch",
                "Checkpoint file index failed verification",
                category=ErrorCategory.INVALID_INPUT,
            )
        for checkpoint_file in checkpoint.files:
            blob = self._blob_path(snapshot_root, checkpoint_file.content_hash)
            _verify_file(
                blob,
                checkpoint_file.content_hash,
                checkpoint_file.byte_size,
                code="checkpoint.blob_corrupt",
            )

    def _restore_file(
        self,
        snapshot_root: Path,
        workspace_root: Path,
        checkpoint_file: CheckpointFile,
    ) -> None:
        blob = self._blob_path(snapshot_root, checkpoint_file.content_hash)
        _verify_file(
            blob,
            checkpoint_file.content_hash,
            checkpoint_file.byte_size,
            code="checkpoint.blob_corrupt",
        )
        target = resolve_project_path(
            workspace_root,
            checkpoint_file.relative_path,
            must_exist=False,
        )
        _ensure_project_parent(workspace_root, checkpoint_file.relative_path)
        if target.exists() or target.is_symlink():
            _require_regular_file(target, code="checkpoint.restore_path_unsafe")
        temporary = target.parent / f".{target.name}.{uuid4().hex}.restore.tmp"
        try:
            with blob.open("rb") as source, temporary.open("xb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
                output.flush()
                os.fsync(output.fileno())
            _verify_file(
                temporary,
                checkpoint_file.content_hash,
                checkpoint_file.byte_size,
                code="checkpoint.restore_verification_failed",
            )
            os.replace(temporary, target)
            _verify_file(
                target,
                checkpoint_file.content_hash,
                checkpoint_file.byte_size,
                code="checkpoint.restore_verification_failed",
            )
        finally:
            temporary.unlink(missing_ok=True)

    def _require_workspace_matches_protection(
        self,
        workspace_root: Path,
        target: ProjectCheckpoint,
        protection: ProjectCheckpoint,
    ) -> None:
        protected = {file.relative_path: file.content_hash for file in protection.files}
        for checkpoint_file in target.files:
            current_hash = self.file_hash(workspace_root, checkpoint_file.relative_path)
            if current_hash != protected.get(checkpoint_file.relative_path):
                raise CheckpointError(
                    "checkpoint.workspace_changed",
                    "Workspace changed after restore confirmation",
                    details={"relative_path": checkpoint_file.relative_path},
                )

    def _blob_path(self, snapshot_root: Path, content_hash: str) -> Path:
        if re.fullmatch(r"[0-9a-f]{64}", content_hash) is None:
            raise CheckpointError(
                "checkpoint.hash_invalid",
                "Checkpoint hash is invalid",
                category=ErrorCategory.INVALID_INPUT,
            )
        return snapshot_root / "blobs" / "sha256" / content_hash[:2] / content_hash

    def _checkpoint_path(
        self,
        snapshot_root: Path,
        project_id: str,
        checkpoint_id: str,
    ) -> Path:
        if _SAFE_ID.fullmatch(project_id) is None or _SAFE_ID.fullmatch(checkpoint_id) is None:
            raise CheckpointError(
                "checkpoint.id_invalid",
                "Checkpoint identity is invalid",
                category=ErrorCategory.INVALID_INPUT,
            )
        return snapshot_root / "checkpoints" / project_id / f"{checkpoint_id}.json"


def _canonical_json(checkpoint: ProjectCheckpoint) -> bytes:
    return json.dumps(
        checkpoint.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _file_index_hash(files: tuple[CheckpointFile, ...]) -> str:
    payload = [file.model_dump(mode="json") for file in files]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _create_or_validate_directory(path: Path, *, parents: bool = False) -> Path:
    try:
        if path.exists() or path.is_symlink():
            metadata = path.lstat()
            if _is_link_or_reparse(metadata) or not stat.S_ISDIR(metadata.st_mode):
                raise CheckpointError(
                    "checkpoint.storage_unsafe",
                    "Checkpoint storage path is unsafe",
                    category=ErrorCategory.INVALID_INPUT,
                )
        else:
            path.mkdir(parents=parents, exist_ok=False)
        resolved = path.resolve(strict=True)
        if resolved != path.absolute():
            raise CheckpointError(
                "checkpoint.storage_unsafe",
                "Checkpoint storage path cannot contain links",
                category=ErrorCategory.INVALID_INPUT,
            )
        return resolved
    except CheckpointError:
        raise
    except OSError:
        raise CheckpointError(
            "checkpoint.storage_unavailable",
            "Checkpoint storage is unavailable",
            category=ErrorCategory.UNAVAILABLE,
        ) from None


def _require_regular_file(path: Path, *, code: str) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError:
        raise CheckpointError(
            code,
            "Checkpoint file is unavailable",
            category=ErrorCategory.INVALID_INPUT,
        ) from None
    if _is_link_or_reparse(metadata) or not stat.S_ISREG(metadata.st_mode):
        raise CheckpointError(
            code,
            "Checkpoint file is unsafe",
            category=ErrorCategory.INVALID_INPUT,
        )
    return metadata


def _verify_file(path: Path, content_hash: str, byte_size: int, *, code: str) -> None:
    metadata = _require_regular_file(path, code=code)
    if metadata.st_size != byte_size:
        raise CheckpointError(code, "Checkpoint file size verification failed")
    if _hash_regular_file(path, byte_size) != content_hash:
        raise CheckpointError(code, "Checkpoint file hash verification failed")


def _hash_regular_file(path: Path, expected_size: int) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            opened = os.fstat(source.fileno())
            if opened.st_size != expected_size:
                raise CheckpointError(
                    "checkpoint.workspace_changed",
                    "Project file changed during verification",
                )
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
            after = os.fstat(source.fileno())
            if not _same_file_version(opened, after):
                raise CheckpointError(
                    "checkpoint.workspace_changed",
                    "Project file changed during verification",
                )
    except CheckpointError:
        raise
    except OSError:
        raise CheckpointError(
            "checkpoint.file_unavailable",
            "Project file could not be verified",
            category=ErrorCategory.UNAVAILABLE,
        ) from None
    return digest.hexdigest()


def _same_file_version(before: os.stat_result, after: os.stat_result) -> bool:
    return (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) == (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )


def _is_link_or_reparse(metadata: os.stat_result) -> bool:
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & _WINDOWS_REPARSE_POINT
    )


def _is_excluded(relative_path: str, excluded_paths: tuple[str, ...]) -> bool:
    if relative_path == ".agent" or relative_path.startswith(".agent/"):
        return True
    return any(
        relative_path == excluded or relative_path.startswith(f"{excluded}/")
        for excluded in excluded_paths
    )


def _ensure_project_parent(workspace_root: Path, relative_path: str) -> None:
    root, _ = validate_direct_workspace_root(workspace_root)
    current = root
    for part in relative_path.split("/")[:-1]:
        current /= part
        if current.exists() or current.is_symlink():
            metadata = current.lstat()
            if _is_link_or_reparse(metadata) or not stat.S_ISDIR(metadata.st_mode):
                raise CheckpointError(
                    "checkpoint.restore_path_unsafe",
                    "Restore target path is unsafe",
                    category=ErrorCategory.INVALID_INPUT,
                )
        else:
            current.mkdir(exist_ok=False)
