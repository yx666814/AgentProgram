from datetime import UTC, datetime
from math import isfinite
from typing import Annotated, Any, Literal, cast

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, field_validator

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


def _ensure_json_value(value: object) -> None:
    value_type = type(value)
    if value is None or value_type in {bool, int, str}:
        return
    if value_type is float:
        if isfinite(cast(float, value)):
            return
        raise ValueError("payload must contain only JSON values")
    if value_type is list:
        for item in cast(list[object], value):
            _ensure_json_value(item)
        return
    if value_type is dict:
        for key, item in cast(dict[object, object], value).items():
            if type(key) is not str:
                raise ValueError("payload must contain only JSON values")
            _ensure_json_value(item)
        return
    raise ValueError("payload must contain only JSON values")


class IpcMessage(BaseModel):
    model_config = ConfigDict(strict=True, hide_input_in_errors=True)

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
        if type(value) is not dict:
            raise ValueError("payload must contain only JSON values")
        _ensure_json_value(value)
        return cast(dict[str, Any], value)
