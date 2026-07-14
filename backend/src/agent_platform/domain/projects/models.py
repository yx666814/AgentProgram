from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

from pydantic import AwareDatetime, Field, field_validator, model_validator

from agent_platform.domain.contracts.base import FrozenContractModel, VersionedContractModel
from agent_platform.domain.contracts.scalars import (
    ContractId,
    PositiveVersion,
    require_project_relative_path,
    require_utc,
)
from agent_platform.domain.shared.json_values import validate_json_payload

ProjectName = Annotated[str, Field(min_length=1, max_length=120)]
ProjectGoal = Annotated[str, Field(min_length=1, max_length=10_000)]
AbsoluteWorkspacePath = Annotated[str, Field(min_length=1, max_length=32_767)]
CommandArgument = Annotated[str, Field(min_length=1, max_length=4096)]
ContentHash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
PreflightCheckCode = Annotated[
    str,
    Field(pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$", max_length=120),
]


class WorkspaceMode(StrEnum):
    MANAGED = "managed"
    DIRECT = "direct"


class ProjectStatus(StrEnum):
    PREFLIGHT_REQUIRED = "preflight_required"
    READY = "ready"
    CLOSED = "closed"


class PreflightStatus(StrEnum):
    PASS = "pass"
    WARNING = "warning"
    NEEDS_FIX = "needs_fix"
    FAIL = "fail"


class CheckpointReason(StrEnum):
    MANUAL = "manual"
    PRE_MUTATION = "pre_mutation"
    PRE_RESTORE = "pre_restore"


class ExternalChangeType(StrEnum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"


class ExternalChangeStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"


class FileConflictStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class ConflictResolution(StrEnum):
    KEEP_USER = "keep_user"
    KEEP_AGENT = "keep_agent"
    MANUAL_MERGE = "manual_merge"


class Project(VersionedContractModel):
    id: ContractId
    name: ProjectName
    goal: ProjectGoal
    status: ProjectStatus
    created_at: AwareDatetime
    updated_at: AwareDatetime
    version: PositiveVersion

    @field_validator("name", "goal")
    @classmethod
    def require_trimmed_text(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("project text must be trimmed")
        return value

    @field_validator("created_at", "updated_at")
    @classmethod
    def require_utc_timestamps(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="project timestamp")

    @model_validator(mode="after")
    def require_timestamp_order(self) -> "Project":
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")
        return self


class Workspace(VersionedContractModel):
    id: ContractId
    project_id: ContractId
    mode: WorkspaceMode
    root_path: AbsoluteWorkspacePath
    canonical_root_path: AbsoluteWorkspacePath
    created_at: AwareDatetime

    @field_validator("root_path", "canonical_root_path")
    @classmethod
    def require_absolute_path(cls, value: str) -> str:
        if value != value.strip() or "\x00" in value or not Path(value).is_absolute():
            raise ValueError("workspace path must be a canonical absolute path")
        return value

    @field_validator("created_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="workspace created_at")


class ProjectRegistration(VersionedContractModel):
    project: Project
    workspace: Workspace

    @model_validator(mode="after")
    def require_matching_project(self) -> "ProjectRegistration":
        if self.workspace.project_id != self.project.id:
            raise ValueError("workspace project_id must match project id")
        return self


class ProjectCommand(VersionedContractModel):
    argv: tuple[CommandArgument, ...]
    working_directory: str | None = None
    timeout_seconds: int = Field(default=900, ge=1, le=86_400)

    @field_validator("argv")
    @classmethod
    def require_safe_arguments(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or any(
            argument != argument.strip() or "\x00" in argument for argument in value
        ):
            raise ValueError("command arguments must be non-empty, trimmed strings")
        return value

    @field_validator("working_directory")
    @classmethod
    def require_relative_working_directory(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_manifest_path(value)


class ProjectManifest(VersionedContractModel):
    project_id: ContractId
    manifest_version: PositiveVersion
    source_paths: tuple[str, ...] = ()
    excluded_paths: tuple[str, ...] = ()
    instruction_paths: tuple[str, ...] = ()
    build_commands: tuple[ProjectCommand, ...] = ()
    test_commands: tuple[ProjectCommand, ...] = ()
    typecheck_commands: tuple[ProjectCommand, ...] = ()

    @field_validator("source_paths", "excluded_paths", "instruction_paths")
    @classmethod
    def require_canonical_unique_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        validated = tuple(_validate_manifest_path(path) for path in value)
        if len(set(validated)) != len(validated):
            raise ValueError("manifest paths must be unique")
        return validated


class ProjectMetadata(VersionedContractModel):
    project_id: ContractId
    workspace_id: ContractId
    workspace_mode: WorkspaceMode
    created_at: AwareDatetime

    @field_validator("created_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="project metadata created_at")


class PersistedProjectManifest(VersionedContractModel):
    manifest: ProjectManifest
    content_hash: ContentHash
    updated_at: AwareDatetime

    @field_validator("updated_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="manifest updated_at")


class PreflightCheck(FrozenContractModel):
    code: PreflightCheckCode
    status: PreflightStatus
    message: Annotated[str, Field(min_length=1, max_length=500)]
    evidence: dict[str, Any] = Field(default_factory=dict)

    @field_validator("evidence", mode="before")
    @classmethod
    def require_json_evidence(cls, value: object) -> dict[str, Any]:
        return validate_json_payload(value)


class ProjectPreflightResult(VersionedContractModel):
    id: ContractId
    project_id: ContractId
    manifest_version: PositiveVersion
    status: PreflightStatus
    checks: tuple[PreflightCheck, ...]
    started_at: AwareDatetime
    completed_at: AwareDatetime

    @field_validator("started_at", "completed_at")
    @classmethod
    def require_utc_timestamps(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="preflight timestamp")

    @model_validator(mode="after")
    def require_consistent_status(self) -> "ProjectPreflightResult":
        if not self.checks:
            raise ValueError("preflight must contain checks")
        if self.completed_at < self.started_at:
            raise ValueError("completed_at must not precede started_at")
        if self.status is not worst_preflight_status(self.checks):
            raise ValueError("preflight status must match the worst check")
        return self


class CheckpointFile(FrozenContractModel):
    relative_path: str
    content_hash: ContentHash
    byte_size: int = Field(ge=0)

    @field_validator("relative_path")
    @classmethod
    def require_canonical_path(cls, value: object) -> str:
        return _validate_manifest_path(value)


class ProjectCheckpoint(VersionedContractModel):
    id: ContractId
    project_id: ContractId
    manifest_version: PositiveVersion
    reason: CheckpointReason
    content_hash: ContentHash
    files: tuple[CheckpointFile, ...]
    total_bytes: int = Field(ge=0)
    created_at: AwareDatetime

    @field_validator("created_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="checkpoint created_at")

    @model_validator(mode="after")
    def require_consistent_file_index(self) -> "ProjectCheckpoint":
        paths = tuple(file.relative_path for file in self.files)
        if paths != tuple(sorted(paths)) or len(set(paths)) != len(paths):
            raise ValueError("checkpoint files must use unique sorted paths")
        if self.total_bytes != sum(file.byte_size for file in self.files):
            raise ValueError("checkpoint total_bytes does not match file index")
        return self


class CheckpointRestoreResult(VersionedContractModel):
    restored_checkpoint_id: ContractId
    protection_checkpoint_id: ContractId
    restored_file_count: int = Field(ge=0)


class ExternalChange(VersionedContractModel):
    id: ContractId
    project_id: ContractId
    relative_path: str
    change_type: ExternalChangeType
    baseline_content_hash: ContentHash | None = None
    current_content_hash: ContentHash | None = None
    status: ExternalChangeStatus = ExternalChangeStatus.OPEN
    detected_at: AwareDatetime

    @field_validator("relative_path")
    @classmethod
    def require_canonical_path(cls, value: object) -> str:
        return _validate_manifest_path(value)

    @field_validator("detected_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="external change detected_at")

    @model_validator(mode="after")
    def require_consistent_hashes(self) -> "ExternalChange":
        baseline = self.baseline_content_hash
        current = self.current_content_hash
        valid = {
            ExternalChangeType.ADDED: baseline is None and current is not None,
            ExternalChangeType.DELETED: baseline is not None and current is None,
            ExternalChangeType.MODIFIED: (
                baseline is not None and current is not None and baseline != current
            ),
        }
        if not valid[self.change_type]:
            raise ValueError("external change hashes do not match change type")
        return self


class FileConflict(VersionedContractModel):
    id: ContractId
    project_id: ContractId
    relative_path: str
    baseline_content_hash: ContentHash | None = None
    user_content_hash: ContentHash | None = None
    agent_content_hash: ContentHash | None = None
    status: FileConflictStatus = FileConflictStatus.OPEN
    resolution: ConflictResolution | None = None
    version: PositiveVersion
    created_at: AwareDatetime
    resolved_at: AwareDatetime | None = None

    @field_validator("relative_path")
    @classmethod
    def require_canonical_path(cls, value: object) -> str:
        return _validate_manifest_path(value)

    @field_validator("created_at", "resolved_at")
    @classmethod
    def require_utc_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return require_utc(value, field_name="file conflict timestamp")

    @model_validator(mode="after")
    def require_consistent_conflict(self) -> "FileConflict":
        if (
            self.user_content_hash == self.baseline_content_hash
            or self.agent_content_hash == self.baseline_content_hash
            or self.user_content_hash == self.agent_content_hash
        ):
            raise ValueError("file conflict requires divergent user and agent changes")
        if self.status is FileConflictStatus.OPEN:
            if self.resolution is not None or self.resolved_at is not None:
                raise ValueError("open conflict cannot have a resolution")
        elif self.resolution is None or self.resolved_at is None:
            raise ValueError("resolved conflict requires resolution metadata")
        return self


class CheckpointRestorePlan(VersionedContractModel):
    current_checkpoint_id: ContractId
    target_checkpoint_id: ContractId
    overwrite_paths: tuple[str, ...]
    preserved_extra_paths: tuple[str, ...]

    @field_validator("overwrite_paths", "preserved_extra_paths")
    @classmethod
    def require_sorted_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        validated = tuple(_validate_manifest_path(path) for path in value)
        if validated != tuple(sorted(set(validated))):
            raise ValueError("restore plan paths must be unique and sorted")
        return validated


def canonical_manifest_document(manifest: ProjectManifest) -> dict[str, Any]:
    return manifest.model_dump(mode="json")


def _validate_manifest_path(value: object) -> str:
    path = require_project_relative_path(value)
    if path == ".agent" or path.startswith(".agent/"):
        raise ValueError(".agent is reserved for AgentProgram metadata")
    return path


def worst_preflight_status(checks: tuple[PreflightCheck, ...]) -> PreflightStatus:
    rank = {
        PreflightStatus.PASS: 0,
        PreflightStatus.WARNING: 1,
        PreflightStatus.NEEDS_FIX: 2,
        PreflightStatus.FAIL: 3,
    }
    return max((check.status for check in checks), key=rank.__getitem__)
