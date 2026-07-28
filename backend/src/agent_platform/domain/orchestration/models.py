from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any

from pydantic import Field, field_validator

from agent_platform.domain.contracts.base import FrozenContractModel, VersionedContractModel
from agent_platform.domain.contracts.scalars import ContractId, ContractName, PositiveVersion
from agent_platform.domain.shared.json_values import validate_json_payload


class OrchestrationFrameType(StrEnum):
    STARTED = "started"
    STAGE_TRANSITIONED = "stage_transitioned"
    TASK_STARTED = "task_started"
    AGENT_RUN_CREATED = "agent_run_created"
    AGENT_FRAME = "agent_frame"
    PLAN_VALIDATED = "plan_validated"
    TOOL_COMPLETED = "tool_completed"
    TASK_COMPLETED = "task_completed"
    ARTIFACT_CREATED = "artifact_created"
    GATE_EVALUATED = "gate_evaluated"
    APPROVAL_REQUIRED = "approval_required"
    HANDOFF_CREATED = "handoff_created"
    COMPLETED = "completed"
    ERROR = "error"


class PlannedToolAction(FrozenContractModel):
    tool_name: ContractName
    arguments: dict[str, Any]
    timeout_seconds: Annotated[int, Field(default=900, ge=1, le=3600)] = 900

    @field_validator("arguments", mode="before")
    @classmethod
    def require_json_arguments(cls, value: object) -> dict[str, Any]:
        return validate_json_payload(value)


class StageExecutionPlan(VersionedContractModel):
    summary: Annotated[str, Field(min_length=1, max_length=4000)]
    artifact_content: Annotated[str, Field(min_length=1, max_length=8_000_000)]
    actions: Annotated[tuple[PlannedToolAction, ...], Field(max_length=64)] = ()

    @field_validator("summary", "artifact_content")
    @classmethod
    def require_trimmed_text(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("execution plan text must be trimmed")
        return value


class OrchestrationFrame(FrozenContractModel):
    type: OrchestrationFrameType
    workflow_id: ContractId
    stage_run_id: ContractId
    sequence: PositiveVersion
    agent_run_id: ContractId | None = None
    task_id: ContractId | None = None
    text: str | None = None
    error_code: str | None = Field(
        default=None,
        max_length=120,
        pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$",
    )
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("data", mode="before")
    @classmethod
    def require_json_data(cls, value: object) -> dict[str, Any]:
        return validate_json_payload(value)
