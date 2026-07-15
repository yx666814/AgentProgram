from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any
from urllib.parse import urlsplit

from pydantic import AwareDatetime, Field, field_validator, model_validator

from agent_platform.domain.contracts.base import FrozenContractModel, VersionedContractModel
from agent_platform.domain.contracts.scalars import (
    ContractId,
    IdempotencyKey,
    PositiveVersion,
    require_utc,
)
from agent_platform.domain.shared.json_values import validate_json_payload

ProfileName = Annotated[str, Field(min_length=1, max_length=120)]
ModelName = Annotated[str, Field(min_length=1, max_length=200)]
CredentialRef = Annotated[
    str,
    Field(min_length=3, max_length=128, pattern=r"^[a-z][a-z0-9_.:-]+$"),
]
MaskedHint = Annotated[str, Field(min_length=1, max_length=40)]
OutputReference = Annotated[str, Field(min_length=1, max_length=500)]
PromptText = Annotated[str, Field(min_length=1, max_length=1_000_000)]
SummaryText = Annotated[str, Field(min_length=1, max_length=200_000)]
ErrorCode = Annotated[
    str,
    Field(max_length=120, pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"),
]
Sha256Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class ModelProvider(StrEnum):
    OPENAI_COMPATIBLE = "openai_compatible"
    ANTHROPIC = "anthropic"
    FAKE = "fake"


class ModelRole(StrEnum):
    PRIMARY = "primary"
    REVIEWER_A = "reviewer_a"
    REVIEWER_B = "reviewer_b"


class ModelPhase(StrEnum):
    P0 = "p0"
    P1 = "p1"
    P2R = "p2r"


class AgentRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL_FAILURE = "partial_failure"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ModelCallStatus(StrEnum):
    PENDING = "pending"
    STREAMING = "streaming"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ModelMessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class StreamFrameType(StrEnum):
    RUN_STARTED = "run_started"
    CALL_STARTED = "call_started"
    CHUNK = "chunk"
    CALL_COMPLETED = "call_completed"
    RUN_COMPLETED = "run_completed"
    ERROR = "error"


class ModelProfile(VersionedContractModel):
    id: ContractId
    name: ProfileName
    provider: ModelProvider
    base_url: Annotated[str, Field(min_length=1, max_length=2048)]
    model: ModelName
    credential_ref: CredentialRef
    masked_hint: MaskedHint
    enabled: bool
    version: PositiveVersion
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @field_validator("name", "model", "masked_hint")
    @classmethod
    def require_trimmed_text(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("model profile text must be trimmed")
        return value

    @field_validator("masked_hint")
    @classmethod
    def require_masked_hint(cls, value: str) -> str:
        if "*" not in value:
            raise ValueError("masked_hint must not contain an unmasked credential")
        return value

    @field_validator("base_url")
    @classmethod
    def require_safe_base_url(cls, value: str) -> str:
        if value != value.strip() or value.endswith("/"):
            raise ValueError("base_url must be trimmed without a trailing slash")
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("base_url must be an HTTP(S) origin or path without credentials")
        return value

    @field_validator("created_at", "updated_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="model profile timestamp")

    @model_validator(mode="after")
    def require_timestamp_order(self) -> ModelProfile:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")
        return self


class RoomModelAssignment(VersionedContractModel):
    room_id: ContractId
    primary_profile_id: ContractId
    reviewer_a_profile_id: ContractId | None = None
    reviewer_b_profile_id: ContractId | None = None
    version: PositiveVersion
    updated_at: AwareDatetime

    @field_validator("updated_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="model assignment updated_at")

    @model_validator(mode="after")
    def require_distinct_profiles(self) -> RoomModelAssignment:
        profile_ids = tuple(
            profile_id
            for profile_id in (
                self.primary_profile_id,
                self.reviewer_a_profile_id,
                self.reviewer_b_profile_id,
            )
            if profile_id is not None
        )
        if len(profile_ids) != len(set(profile_ids)):
            raise ValueError("room model assignment profiles must be distinct")
        return self


class AgentRun(VersionedContractModel):
    id: ContractId
    workflow_id: ContractId
    room_id: ContractId
    request_key: IdempotencyKey
    formal: bool
    status: AgentRunStatus
    final_output_ref: OutputReference | None = None
    final_output_hash: Sha256Digest | None = None
    final_output_bytes: int | None = Field(default=None, ge=0)
    error_code: ErrorCode | None = None
    version: PositiveVersion
    created_at: AwareDatetime
    completed_at: AwareDatetime | None = None

    @field_validator("created_at", "completed_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return require_utc(value, field_name="agent run timestamp")

    @model_validator(mode="after")
    def require_terminal_metadata(self) -> AgentRun:
        terminal = self.status in {
            AgentRunStatus.SUCCEEDED,
            AgentRunStatus.PARTIAL_FAILURE,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
        }
        if terminal != (self.completed_at is not None):
            raise ValueError("terminal agent run state and completed_at must agree")
        output_fields = (
            self.final_output_ref,
            self.final_output_hash,
            self.final_output_bytes,
        )
        if any(value is not None for value in output_fields) and not all(
            value is not None for value in output_fields
        ):
            raise ValueError("agent run output metadata must be complete")
        if self.status is AgentRunStatus.SUCCEEDED and self.final_output_ref is None:
            raise ValueError("successful agent runs require final output")
        return self


class ModelCall(VersionedContractModel):
    id: ContractId
    agent_run_id: ContractId
    profile_id: ContractId
    role: ModelRole
    phase: ModelPhase
    status: ModelCallStatus
    prompt_hash: Sha256Digest
    output_ref: OutputReference | None = None
    output_hash: Sha256Digest | None = None
    output_bytes: int | None = Field(default=None, ge=0)
    error_code: ErrorCode | None = None
    version: PositiveVersion
    started_at: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None

    @field_validator("started_at", "completed_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return require_utc(value, field_name="model call timestamp")

    @model_validator(mode="after")
    def require_call_metadata(self) -> ModelCall:
        if self.status is ModelCallStatus.PENDING:
            if self.started_at is not None or self.completed_at is not None:
                raise ValueError("pending calls cannot have lifecycle timestamps")
        else:
            if self.started_at is None:
                raise ValueError("started model calls require started_at")
        terminal = self.status in {
            ModelCallStatus.SUCCEEDED,
            ModelCallStatus.FAILED,
            ModelCallStatus.CANCELLED,
        }
        if terminal != (self.completed_at is not None):
            raise ValueError("terminal model call state and completed_at must agree")
        output_fields = (self.output_ref, self.output_hash, self.output_bytes)
        if any(value is not None for value in output_fields) and not all(
            value is not None for value in output_fields
        ):
            raise ValueError("model call output metadata must be complete")
        if self.status is ModelCallStatus.SUCCEEDED and self.output_ref is None:
            raise ValueError("successful model calls require output")
        return self


class UsageRecord(VersionedContractModel):
    model_call_id: ContractId
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    recorded_at: AwareDatetime

    @field_validator("recorded_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="usage recorded_at")

    @model_validator(mode="after")
    def require_total(self) -> UsageRecord:
        if self.total_tokens != self.input_tokens + self.output_tokens:
            raise ValueError("total_tokens must equal input plus output tokens")
        return self


class ConversationSummary(VersionedContractModel):
    id: ContractId
    room_id: ContractId
    through_sequence: PositiveVersion
    content: SummaryText
    content_hash: Sha256Digest
    created_at: AwareDatetime

    @field_validator("content")
    @classmethod
    def require_trimmed_content(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("summary content must be trimmed")
        return value

    @field_validator("created_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="summary created_at")


class ModelMessage(FrozenContractModel):
    role: ModelMessageRole
    content: PromptText


class ModelInvocation(FrozenContractModel):
    model: ModelName
    messages: tuple[ModelMessage, ...]
    max_output_tokens: int = Field(default=4096, ge=1, le=1_000_000)
    temperature: float = Field(default=0.2, ge=0, le=2)

    @field_validator("messages")
    @classmethod
    def require_messages(cls, value: tuple[ModelMessage, ...]) -> tuple[ModelMessage, ...]:
        if not value:
            raise ValueError("model invocation requires messages")
        return value


class ModelChunk(FrozenContractModel):
    text: str = Field(default="", max_length=1_000_000)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class AgentStreamFrame(FrozenContractModel):
    type: StreamFrameType
    run_id: ContractId
    sequence: PositiveVersion
    role: ModelRole | None = None
    phase: ModelPhase | None = None
    text: str | None = None
    status: AgentRunStatus | ModelCallStatus | None = None
    error_code: ErrorCode | None = None
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("data", mode="before")
    @classmethod
    def require_json_data(cls, value: object) -> dict[str, Any]:
        return validate_json_payload(value)


class AgentRunSnapshot(VersionedContractModel):
    run: AgentRun
    calls: tuple[ModelCall, ...]
    usage: tuple[UsageRecord, ...]
