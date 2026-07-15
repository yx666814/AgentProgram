from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field, field_validator

from agent_platform.domain.contracts import StagePathScope
from agent_platform.domain.contracts.base import FrozenContractModel
from agent_platform.domain.contracts.scalars import ContractName, require_project_relative_path


class ToolOperation(StrEnum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    CREATE_DIRECTORY = "create_directory"
    COMMAND = "command"


class ToolDefinition(FrozenContractModel):
    name: ContractName
    capability: ContractName
    operation: ToolOperation
    allowed_scopes: tuple[StagePathScope, ...] = ()
    mutating: bool
    max_timeout_seconds: Annotated[int, Field(ge=1, le=3600)]


class FileToolResult(FrozenContractModel):
    relative_path: str
    content_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    byte_size: Annotated[int, Field(ge=0)]

    @field_validator("relative_path")
    @classmethod
    def validate_path(cls, value: object) -> str:
        return require_project_relative_path(value)


class ProcessToolResult(FrozenContractModel):
    exit_code: int
    stdout_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    stderr_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    stdout_bytes: Annotated[int, Field(ge=0)]
    stderr_bytes: Annotated[int, Field(ge=0)]
