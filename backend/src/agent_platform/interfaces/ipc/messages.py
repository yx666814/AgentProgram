from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, BaseModel, Field

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
    protocol_version: Literal[1] = 1
    message_id: NonEmptyString
    correlation_id: NonEmptyString | None = None
    sequence: int = Field(ge=0)
    project_id: NonEmptyString
    task_id: NonEmptyString | None = None
    type: MessageType
    timestamp: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] = Field(default_factory=dict)
