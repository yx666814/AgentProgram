from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, field_validator

from agent_platform.domain.contracts.base import VersionedContractModel
from agent_platform.domain.contracts.scalars import (
    ContractId,
    ContractName,
    IdempotencyKey,
    require_project_relative_path,
    require_utc,
)
from agent_platform.domain.contracts.stages import Stage

CommandArgument = Annotated[str, Field(min_length=1)]
CommandIntent = Annotated[tuple[CommandArgument, ...], Field(min_length=1)]


class CapabilityRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CapabilityRequest(VersionedContractModel):
    request_id: ContractId
    correlation_id: ContractId
    project_id: ContractId
    workflow_id: ContractId
    stage_run_id: ContractId
    task_id: ContractId
    requester_role: Stage
    requested_capability: ContractName
    reason: Annotated[str, Field(min_length=1, max_length=2000)]
    target_paths: tuple[str, ...] = ()
    proposed_command: CommandIntent | None = None
    expected_changes: Annotated[str, Field(min_length=1, max_length=2000)]
    risk_level: CapabilityRisk
    idempotency_key: IdempotencyKey
    requested_at: AwareDatetime
    expires_after_task: Literal[True] = True

    @field_validator("reason", "expected_changes")
    @classmethod
    def validate_explanation(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("explanation must not be blank")
        return value

    @field_validator("target_paths")
    @classmethod
    def validate_target_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        paths = tuple(require_project_relative_path(path) for path in value)
        if len(paths) != len(set(paths)):
            raise ValueError("target paths must not contain duplicates")
        return paths

    @field_validator("requested_at")
    @classmethod
    def validate_requested_at(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="requested_at")

    @field_validator("expires_after_task", mode="before")
    @classmethod
    def validate_expiry(cls, value: object) -> bool:
        if type(value) is not bool or value is not True:
            raise ValueError("capability request must expire after task")
        return True
