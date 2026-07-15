from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from agent_platform.domain.shared.json_values import validate_json_payload

NonEmptyString = Annotated[str, Field(min_length=1)]
EventType = Annotated[
    str,
    Field(max_length=120, pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"),
]
EventContextId = Annotated[str, Field(min_length=1, max_length=120)]
EventEntityId = Annotated[str, Field(min_length=1, max_length=80)]
PositiveEventId = Annotated[int, Field(gt=0)]


class ActorType(StrEnum):
    SYSTEM = "system"
    USER = "user"
    WORKER = "worker"
    MODEL = "model"
    TOOL = "tool"


class EventSource(StrEnum):
    BACKEND = "backend"
    DESKTOP = "desktop"
    WORKER = "worker"
    MODEL = "model"
    TOOL = "tool"


class ActorRef(BaseModel):
    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        hide_input_in_errors=True,
    )

    type: ActorType
    id: EventEntityId | None = None


class EventEnvelope(BaseModel):
    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        hide_input_in_errors=True,
    )

    schema_version: Literal[1]
    event_id: PositiveEventId | None = None
    event_type: EventType
    correlation_id: EventContextId
    causation_id: EventContextId | None = None
    actor: ActorRef
    source: EventSource
    occurred_at: AwareDatetime
    project_id: EventEntityId | None = None
    workflow_id: EventEntityId | None = None
    room_id: EventEntityId | None = None
    task_id: EventEntityId | None = None
    payload: dict[str, Any]

    @field_validator("schema_version", mode="before")
    @classmethod
    def validate_schema_version(cls, value: object) -> int:
        if type(value) is not int:
            raise ValueError("schema version must be integer 1")
        return value

    @field_validator("occurred_at")
    @classmethod
    def validate_utc_timestamp(cls, value: datetime) -> datetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("occurred_at must use UTC")
        return value

    @field_validator("payload", mode="before")
    @classmethod
    def validate_payload(cls, value: object) -> dict[str, Any]:
        return validate_json_payload(value)
