from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from agent_platform.domain.shared.errors import DomainError, ErrorCategory

_REFERENCE = re.compile(r"^[0-9a-f]{2}/[0-9a-f]{64}\.txt$")
_WINDOWS_REPARSE_POINT = 0x400


@dataclass(frozen=True, slots=True)
class StoredModelOutput:
    reference: str
    content_hash: str
    byte_size: int


class ModelOutputStore:
    def __init__(self, root: Path, *, max_output_bytes: int) -> None:
        if max_output_bytes < 1:
            raise ValueError("model output limit must be positive")
        self._root = root
        self._max_output_bytes = max_output_bytes

    def initialize(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        _require_directory(self._root)
        (self._root / "temp").mkdir(exist_ok=True)
        _require_directory(self._root / "temp")

    def write(self, content: str) -> StoredModelOutput:
        data = content.encode("utf-8", errors="strict")
        if not data:
            raise DomainError(
                code="model.output_empty",
                message="Model output is empty",
                category=ErrorCategory.UNAVAILABLE,
            )
        if len(data) > self._max_output_bytes:
            raise DomainError(
                code="model.output_too_large",
                message="Model output exceeds the configured limit",
                category=ErrorCategory.INVALID_INPUT,
            )
        self.initialize()
        content_hash = hashlib.sha256(data).hexdigest()
        reference = f"{content_hash[:2]}/{content_hash}.txt"
        parent = self._root / content_hash[:2]
        parent.mkdir(exist_ok=True)
        _require_directory(parent)
        target = self._root / reference
        if target.exists():
            _verify_output(target, content_hash, len(data))
            return StoredModelOutput(reference, content_hash, len(data))
        temporary = self._root / "temp" / f"output-{uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            try:
                os.replace(temporary, target)
            except OSError:
                if not target.exists():
                    raise
            _verify_output(target, content_hash, len(data))
        except DomainError:
            raise
        except OSError:
            raise DomainError(
                code="model.output_storage_unavailable",
                message="Model output storage is unavailable",
                category=ErrorCategory.UNAVAILABLE,
            ) from None
        finally:
            temporary.unlink(missing_ok=True)
        return StoredModelOutput(reference, content_hash, len(data))

    def read(self, reference: str, expected_hash: str) -> str:
        if _REFERENCE.fullmatch(reference) is None or reference[3:67] != expected_hash:
            raise DomainError(
                code="model.output_reference_invalid",
                message="Model output reference is invalid",
                category=ErrorCategory.INVALID_INPUT,
            )
        target = self._root / Path(reference)
        try:
            metadata = target.lstat()
            if _is_link_or_reparse(metadata) or not stat.S_ISREG(metadata.st_mode):
                raise OSError
            data = target.read_bytes()
            if len(data) > self._max_output_bytes:
                raise OSError
            if hashlib.sha256(data).hexdigest() != expected_hash:
                raise OSError
            return data.decode("utf-8", errors="strict")
        except (OSError, UnicodeError):
            raise DomainError(
                code="model.output_unavailable",
                message="Model output could not be read or verified",
                category=ErrorCategory.UNAVAILABLE,
            ) from None


def _require_directory(path: Path) -> None:
    metadata = path.lstat()
    if _is_link_or_reparse(metadata) or not stat.S_ISDIR(metadata.st_mode):
        raise DomainError(
            code="model.output_storage_unsafe",
            message="Model output storage path is unsafe",
            category=ErrorCategory.UNAVAILABLE,
        )


def _verify_output(path: Path, content_hash: str, byte_size: int) -> None:
    metadata = path.lstat()
    if (
        _is_link_or_reparse(metadata)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size != byte_size
        or hashlib.sha256(path.read_bytes()).hexdigest() != content_hash
    ):
        raise DomainError(
            code="model.output_verification_failed",
            message="Model output verification failed",
            category=ErrorCategory.UNAVAILABLE,
        )


def _is_link_or_reparse(metadata: os.stat_result) -> bool:
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & _WINDOWS_REPARSE_POINT
    )
