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
_MAX_JSON_DEPTH = 64


def _ensure_json_value(
    value: object,
    active_container_ids: set[int],
    depth: int,
) -> None:
    if depth > _MAX_JSON_DEPTH:
        raise ValueError("payload must contain only JSON values")
    value_type = type(value)
    if value is None or value_type in {bool, int, str}:
        return
    if value_type is float:
        if isfinite(cast(float, value)):
            return
        raise ValueError("payload must contain only JSON values")
    if value_type is list:
        container_id = id(value)
        if container_id in active_container_ids:
            raise ValueError("payload must contain only JSON values")
        active_container_ids.add(container_id)
        try:
            for item in cast(list[object], value):
                _ensure_json_value(item, active_container_ids, depth + 1)
        finally:
            active_container_ids.remove(container_id)
        return
    if value_type is dict:
        container_id = id(value)
        if container_id in active_container_ids:
            raise ValueError("payload must contain only JSON values")
        active_container_ids.add(container_id)
        try:
            for key, item in cast(dict[object, object], value).items():
                if type(key) is not str:
                    raise ValueError("payload must contain only JSON values")
                _ensure_json_value(item, active_container_ids, depth + 1)
        finally:
            active_container_ids.remove(container_id)
        return
    raise ValueError("payload must contain only JSON values")


def validate_json_payload(value: object) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError("payload must contain only JSON values")
    _ensure_json_value(value, set(), 0)
    return cast(dict[str, Any], value)


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
        return validate_json_payload(value)
