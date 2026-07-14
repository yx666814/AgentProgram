from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

from pydantic import AwareDatetime, Field, field_validator, model_validator

from agent_platform.domain.contracts.base import VersionedContractModel
from agent_platform.domain.contracts.scalars import (
    ContractId,
    PositiveVersion,
    require_project_relative_path,
    require_utc,
)

ProjectName = Annotated[str, Field(min_length=1, max_length=120)]
ProjectGoal = Annotated[str, Field(min_length=1, max_length=10_000)]
AbsoluteWorkspacePath = Annotated[str, Field(min_length=1, max_length=32_767)]
CommandArgument = Annotated[str, Field(min_length=1, max_length=4096)]
ContentHash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class WorkspaceMode(StrEnum):
    MANAGED = "managed"
    DIRECT = "direct"


class ProjectStatus(StrEnum):
    PREFLIGHT_REQUIRED = "preflight_required"
    READY = "ready"
    CLOSED = "closed"


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


def canonical_manifest_document(manifest: ProjectManifest) -> dict[str, Any]:
    return manifest.model_dump(mode="json")


def _validate_manifest_path(value: object) -> str:
    path = require_project_relative_path(value)
    if path == ".agent" or path.startswith(".agent/"):
        raise ValueError(".agent is reserved for AgentProgram metadata")
    return path
