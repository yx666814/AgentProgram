from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import AwareDatetime, Field, field_validator, model_validator

from agent_platform.domain.contracts.base import VersionedContractModel
from agent_platform.domain.contracts.scalars import ContractId, PositiveVersion, require_utc

ProjectName = Annotated[str, Field(min_length=1, max_length=120)]
ProjectGoal = Annotated[str, Field(min_length=1, max_length=10_000)]
AbsoluteWorkspacePath = Annotated[str, Field(min_length=1, max_length=32_767)]


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
