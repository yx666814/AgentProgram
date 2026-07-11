from datetime import UTC, datetime
from typing import Any, Literal

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


class IpcMessage(BaseModel):
    protocol_version: Literal[1] = 1
    message_id: str = Field(min_length=1)
    correlation_id: str | None = None
    sequence: int = Field(ge=0)
    project_id: str = Field(min_length=1)
    task_id: str | None = None
    type: MessageType
    timestamp: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] = Field(default_factory=dict)
