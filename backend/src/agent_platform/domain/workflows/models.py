from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import AwareDatetime, Field, field_validator, model_validator

from agent_platform.domain.contracts import Stage, StageRunState
from agent_platform.domain.contracts.base import VersionedContractModel
from agent_platform.domain.contracts.scalars import ContractId, PositiveVersion, require_utc
from agent_platform.domain.governance import ExecutionMode
from agent_platform.domain.shared.json_values import validate_json_payload

WorkflowTitle = Annotated[str, Field(min_length=1, max_length=200)]
MessageContent = Annotated[str, Field(min_length=1, max_length=100_000)]


class WorkflowStatus(StrEnum):
    CREATED = "created"
    PREFLIGHT_FAILED = "preflight_failed"
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    WARNING_BLOCKED = "warning_blocked"
    PAUSED = "paused"
    EXTERNAL_CONFLICT = "external_conflict"
    INTERRUPTED = "interrupted"
    FAILED = "failed"
    STOPPED = "stopped"
    ABANDONED = "abandoned"
    COMPLETED = "completed"


class RoomStatus(StrEnum):
    ACTIVE = "active"
    CONSULTATION = "consultation"
    ARCHIVED = "archived"


class MessageAuthor(StrEnum):
    USER = "user"
    SYSTEM = "system"
    AGENT = "agent"


class MessageKind(StrEnum):
    DISCUSSION = "discussion"
    CONSULTATION = "consultation"
    CORRECTION = "correction"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Workflow(VersionedContractModel):
    id: ContractId
    project_id: ContractId
    title: WorkflowTitle
    status: WorkflowStatus
    execution_mode: ExecutionMode
    current_stage: Stage
    version: PositiveVersion
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @field_validator("title")
    @classmethod
    def require_trimmed_title(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("workflow title must be trimmed")
        return value

    @field_validator("created_at", "updated_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="workflow timestamp")

    @model_validator(mode="after")
    def require_timestamp_order(self) -> Workflow:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")
        return self


class StageRun(VersionedContractModel):
    id: ContractId
    workflow_id: ContractId
    stage: Stage
    attempt: PositiveVersion
    state: StageRunState
    version: PositiveVersion
    created_at: AwareDatetime
    started_at: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None

    @field_validator("created_at", "started_at", "completed_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return require_utc(value, field_name="stage run timestamp")

    @model_validator(mode="after")
    def require_timestamps_match_state(self) -> StageRun:
        if self.started_at is not None and self.started_at < self.created_at:
            raise ValueError("started_at must not precede created_at")
        if self.completed_at is not None:
            if self.started_at is None or self.completed_at < self.started_at:
                raise ValueError("completed_at requires an ordered started_at")
            if self.state is not StageRunState.COMPLETED:
                raise ValueError("only completed stage runs have completed_at")
        if self.state is StageRunState.COMPLETED and self.completed_at is None:
            raise ValueError("completed stage runs require completed_at")
        return self


class Room(VersionedContractModel):
    id: ContractId
    workflow_id: ContractId
    stage_run_id: ContractId
    stage: Stage
    status: RoomStatus
    next_sequence: PositiveVersion
    version: PositiveVersion
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="room timestamp")

    @model_validator(mode="after")
    def require_timestamp_order(self) -> Room:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")
        return self


class Message(VersionedContractModel):
    id: ContractId
    room_id: ContractId
    sequence: PositiveVersion
    author: MessageAuthor
    kind: MessageKind
    content: MessageContent
    correction_of_id: ContractId | None = None
    created_at: AwareDatetime

    @field_validator("content")
    @classmethod
    def require_trimmed_content(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("message content must be trimmed")
        return value

    @field_validator("created_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="message created_at")

    @model_validator(mode="after")
    def require_correction_reference(self) -> Message:
        if (self.kind is MessageKind.CORRECTION) != (self.correction_of_id is not None):
            raise ValueError("correction messages require exactly one original message")
        if self.correction_of_id == self.id:
            raise ValueError("a message cannot correct itself")
        return self


class WorkflowTask(VersionedContractModel):
    id: ContractId
    workflow_id: ContractId
    stage_run_id: ContractId
    room_id: ContractId
    title: WorkflowTitle
    status: TaskStatus
    payload: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    version: PositiveVersion
    created_at: AwareDatetime
    started_at: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None

    @field_validator("title")
    @classmethod
    def require_trimmed_title(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("task title must be trimmed")
        return value

    @field_validator("payload", "result", mode="before")
    @classmethod
    def require_json_document(cls, value: object) -> dict[str, Any] | None:
        if value is None:
            return None
        return validate_json_payload(value)

    @field_validator("created_at", "started_at", "completed_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return require_utc(value, field_name="task timestamp")

    @model_validator(mode="after")
    def require_lifecycle_timestamps(self) -> WorkflowTask:
        if self.started_at is not None and self.started_at < self.created_at:
            raise ValueError("started_at must not precede created_at")
        terminal = self.status in {
            TaskStatus.SUCCEEDED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }
        if terminal != (self.completed_at is not None):
            raise ValueError("terminal task state and completed_at must agree")
        if self.completed_at is not None and self.completed_at < self.created_at:
            raise ValueError("completed_at must not precede created_at")
        if self.status in {TaskStatus.RUNNING, TaskStatus.SUCCEEDED, TaskStatus.FAILED}:
            if self.started_at is None:
                raise ValueError("running and executed tasks require started_at")
        return self


class WorkflowSnapshot(VersionedContractModel):
    workflow: Workflow
    stage_runs: tuple[StageRun, ...]
    rooms: tuple[Room, ...]

    @model_validator(mode="after")
    def require_consistent_graph(self) -> WorkflowSnapshot:
        run_ids = {run.id for run in self.stage_runs}
        if len(run_ids) != len(self.stage_runs):
            raise ValueError("stage run ids must be unique")
        if any(run.workflow_id != self.workflow.id for run in self.stage_runs):
            raise ValueError("stage runs must belong to the workflow")
        if any(
            room.workflow_id != self.workflow.id or room.stage_run_id not in run_ids
            for room in self.rooms
        ):
            raise ValueError("rooms must belong to a stage run in the workflow")
        return self
