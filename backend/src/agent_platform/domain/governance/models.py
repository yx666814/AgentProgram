from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Self

from pydantic import AwareDatetime, Field, field_validator, model_validator

from agent_platform.domain.contracts import Stage
from agent_platform.domain.contracts.base import FrozenContractModel, VersionedContractModel
from agent_platform.domain.contracts.scalars import (
    ContractId,
    ContractName,
    PositiveVersion,
    require_project_relative_path,
    require_utc,
)
from agent_platform.domain.shared.json_values import validate_json_payload

ContentHash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
NonBlankText = Annotated[str, Field(min_length=1, max_length=4000)]


class ExecutionMode(StrEnum):
    MANUAL = "manual"
    AUTONOMOUS = "autonomous"


class CapabilityRequestStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ApprovalKind(StrEnum):
    CAPABILITY = "capability"
    QUALITY_GATE = "quality_gate"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ToolCallStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    INTERRUPTED = "interrupted"


class ArtifactStatus(StrEnum):
    DRAFT = "draft"
    LOCKED = "locked"
    SUPERSEDED = "superseded"
    INVALIDATED = "invalidated"


class GateStatus(StrEnum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


class GateResolution(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    AUTOMATIC = "automatic"
    REWRITE_REQUIRED = "rewrite_required"


class GateIssueSeverity(StrEnum):
    WARNING = "warning"
    ERROR = "error"


class HandoffStatus(StrEnum):
    ACTIVE = "active"
    INVALIDATED = "invalidated"


class ChangeRequestStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    SUPERSEDED = "superseded"


class RecoveryStatus(StrEnum):
    PENDING = "pending"
    RESUMED = "resumed"
    DISCARDED = "discarded"


class CapabilityRequestRecord(VersionedContractModel):
    id: ContractId
    project_id: ContractId
    workflow_id: ContractId
    stage_run_id: ContractId
    task_id: ContractId
    stage: Stage
    capability: ContractName
    reason: NonBlankText
    target_paths: tuple[str, ...] = ()
    command: tuple[str, ...] | None = None
    status: CapabilityRequestStatus
    risk_level: str
    idempotency_key: str
    version: PositiveVersion
    requested_at: AwareDatetime
    decided_at: AwareDatetime | None = None
    decision_reason: str | None = None

    @field_validator("target_paths")
    @classmethod
    def validate_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        paths = tuple(require_project_relative_path(path) for path in value)
        if len(paths) != len(set(paths)):
            raise ValueError("target paths must be unique")
        return paths

    @field_validator("requested_at", "decided_at")
    @classmethod
    def validate_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return require_utc(value, field_name="capability request timestamp")

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        decided = self.status is not CapabilityRequestStatus.PENDING
        if decided != (self.decided_at is not None):
            raise ValueError("capability decision state and timestamp must agree")
        return self


class Approval(VersionedContractModel):
    id: ContractId
    project_id: ContractId
    workflow_id: ContractId
    kind: ApprovalKind
    target_id: ContractId
    status: ApprovalStatus
    version: PositiveVersion
    requested_at: AwareDatetime
    decided_at: AwareDatetime | None = None
    reason: str | None = None

    @field_validator("requested_at", "decided_at")
    @classmethod
    def validate_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return require_utc(value, field_name="approval timestamp")

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        decided = self.status is not ApprovalStatus.PENDING
        if decided != (self.decided_at is not None):
            raise ValueError("approval decision state and timestamp must agree")
        return self


class ToolCall(VersionedContractModel):
    id: ContractId
    project_id: ContractId
    workflow_id: ContractId
    stage_run_id: ContractId
    task_id: ContractId
    tool_name: ContractName
    capability: ContractName
    idempotency_key: str
    arguments_hash: ContentHash
    status: ToolCallStatus
    capability_request_id: ContractId | None = None
    result: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    started_at: AwareDatetime
    completed_at: AwareDatetime | None = None

    @field_validator("result", mode="before")
    @classmethod
    def validate_result(cls, value: object) -> dict[str, Any]:
        return validate_json_payload(value)

    @field_validator("started_at", "completed_at")
    @classmethod
    def validate_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return require_utc(value, field_name="tool call timestamp")

    @model_validator(mode="after")
    def validate_terminal_state(self) -> Self:
        terminal = self.status is not ToolCallStatus.RUNNING
        if terminal != (self.completed_at is not None):
            raise ValueError("tool call terminal state and timestamp must agree")
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("tool call completion cannot precede start")
        return self


class Artifact(VersionedContractModel):
    id: ContractId
    project_id: ContractId
    workflow_id: ContractId
    stage: Stage
    name: Annotated[str, Field(min_length=1, max_length=160)]
    relative_path: str
    created_at: AwareDatetime

    @field_validator("relative_path")
    @classmethod
    def validate_path(cls, value: object) -> str:
        return require_project_relative_path(value)

    @field_validator("created_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="artifact created_at")


class ArtifactVersion(VersionedContractModel):
    id: ContractId
    artifact_id: ContractId
    stage_run_id: ContractId
    version: PositiveVersion
    content_hash: ContentHash
    byte_size: Annotated[int, Field(ge=0)]
    status: ArtifactStatus
    supersedes_id: ContractId | None = None
    checkpoint_id: ContractId | None = None
    created_at: AwareDatetime
    locked_at: AwareDatetime | None = None
    invalidated_at: AwareDatetime | None = None
    invalidation_reason: str | None = None

    @field_validator("created_at", "locked_at", "invalidated_at")
    @classmethod
    def validate_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return require_utc(value, field_name="artifact version timestamp")


class GateIssue(FrozenContractModel):
    code: ContractName
    severity: GateIssueSeverity
    message: Annotated[str, Field(min_length=1, max_length=500)]
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("details", mode="before")
    @classmethod
    def validate_details(cls, value: object) -> dict[str, Any]:
        return validate_json_payload(value)


class QualityGateRun(VersionedContractModel):
    id: ContractId
    project_id: ContractId
    workflow_id: ContractId
    stage_run_id: ContractId
    status: GateStatus
    resolution: GateResolution
    issues: tuple[GateIssue, ...]
    artifact_version_ids: tuple[ContractId, ...]
    version: PositiveVersion
    evaluated_at: AwareDatetime
    resolved_at: AwareDatetime | None = None

    @field_validator("evaluated_at", "resolved_at")
    @classmethod
    def validate_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return require_utc(value, field_name="quality gate timestamp")


class HandoffPacket(VersionedContractModel):
    id: ContractId
    project_id: ContractId
    workflow_id: ContractId
    from_stage_run_id: ContractId
    from_stage: Stage
    to_stage: Stage | None
    gate_run_id: ContractId
    checkpoint_id: ContractId
    artifact_version_ids: tuple[ContractId, ...]
    content_hash: ContentHash
    status: HandoffStatus
    created_at: AwareDatetime
    invalidated_at: AwareDatetime | None = None
    invalidation_reason: str | None = None

    @field_validator("created_at", "invalidated_at")
    @classmethod
    def validate_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return require_utc(value, field_name="handoff timestamp")


class ChangeRequest(VersionedContractModel):
    id: ContractId
    project_id: ContractId
    workflow_id: ContractId
    source_stage_run_id: ContractId
    target_stage: Stage
    gate_run_id: ContractId | None = None
    reason: NonBlankText
    status: ChangeRequestStatus
    input_artifact_version_ids: tuple[ContractId, ...]
    created_at: AwareDatetime
    resolved_at: AwareDatetime | None = None

    @field_validator("created_at", "resolved_at")
    @classmethod
    def validate_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return require_utc(value, field_name="change request timestamp")


class RecoveryRecord(VersionedContractModel):
    id: ContractId
    project_id: ContractId
    workflow_id: ContractId
    stage_run_id: ContractId | None = None
    status: RecoveryStatus
    interrupted_tasks: int = Field(ge=0)
    interrupted_agent_runs: int = Field(ge=0)
    interrupted_tool_calls: int = Field(ge=0)
    detected_at: AwareDatetime
    resolved_at: AwareDatetime | None = None

    @field_validator("detected_at", "resolved_at")
    @classmethod
    def validate_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return require_utc(value, field_name="recovery timestamp")
