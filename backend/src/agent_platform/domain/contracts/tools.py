from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Self

from pydantic import AwareDatetime, Field, ValidationInfo, field_validator, model_validator

from agent_platform.domain.contracts.base import FrozenContractModel, VersionedContractModel
from agent_platform.domain.contracts.scalars import (
    ContractId,
    ContractName,
    IdempotencyKey,
    require_utc,
)
from agent_platform.domain.contracts.stages import Stage
from agent_platform.domain.events import ActorRef
from agent_platform.domain.shared.errors import ErrorCategory
from agent_platform.domain.shared.json_values import validate_json_payload


class ToolExecutionRequest(VersionedContractModel):
    request_id: ContractId
    correlation_id: ContractId
    causation_id: ContractId | None = None
    project_id: ContractId
    workflow_id: ContractId
    stage_run_id: ContractId
    task_id: ContractId
    stage: Stage
    actor: ActorRef
    tool_name: ContractName
    required_capability: ContractName
    idempotency_key: IdempotencyKey
    requested_at: AwareDatetime
    timeout_seconds: Annotated[int, Field(ge=1, le=3600)]
    arguments: dict[str, Any] = Field(default_factory=dict)

    @field_validator("requested_at")
    @classmethod
    def validate_requested_at(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="requested_at")

    @field_validator("arguments", mode="before")
    @classmethod
    def validate_arguments(cls, value: object) -> dict[str, Any]:
        return validate_json_payload(value)


class ToolExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class ToolFailure(FrozenContractModel):
    code: ContractName
    category: ErrorCategory
    message: Annotated[str, Field(min_length=1, max_length=1000)]
    details: dict[str, Any] = Field(default_factory=dict)
    retryable: bool = False

    @field_validator("details", mode="before")
    @classmethod
    def validate_details(cls, value: object) -> dict[str, Any]:
        return validate_json_payload(value)


class ToolResult(VersionedContractModel):
    request_id: ContractId
    idempotency_key: IdempotencyKey
    status: ToolExecutionStatus
    started_at: AwareDatetime
    completed_at: AwareDatetime
    output: dict[str, Any] = Field(default_factory=dict)
    failure: ToolFailure | None = None

    @field_validator("started_at", "completed_at")
    @classmethod
    def validate_timestamp(cls, value: datetime, info: ValidationInfo) -> datetime:
        field_name = info.field_name
        if field_name is None:
            raise TypeError("timestamp validator requires a field name")
        return require_utc(value, field_name=field_name)

    @field_validator("output", mode="before")
    @classmethod
    def validate_output(cls, value: object) -> dict[str, Any]:
        return validate_json_payload(value)

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("completed_at cannot precede started_at")
        if self.status is ToolExecutionStatus.SUCCEEDED:
            if self.failure is not None:
                raise ValueError("successful tool result cannot include failure")
        elif self.failure is None:
            raise ValueError("unsuccessful tool result must include failure")
        return self
