from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, field_validator

from agent_platform.domain.shared.json_values import validate_json_payload

MessageType = Literal[
    "command",
    "response",
    "event",
    "ack",
    "heartbeat",
    "cancel",
    "shutdown",
]
NonEmptyString = Annotated[str, Field(min_length=1)]


class IpcMessage(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)

    protocol_version: Literal[1] = 1
    message_id: NonEmptyString
    correlation_id: NonEmptyString | None = None
    sequence: StrictInt = Field(ge=0)
    project_id: NonEmptyString
    task_id: NonEmptyString | None = None
    type: MessageType
    timestamp: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("protocol_version", mode="before")
    @classmethod
    def validate_protocol_version(cls, value: object) -> int:
        if type(value) is not int:
            raise ValueError("protocol version must be integer 1")
        return value

    @field_validator("payload", mode="before")
    @classmethod
    def validate_payload(cls, value: object) -> dict[str, Any]:
        return validate_json_payload(value)
