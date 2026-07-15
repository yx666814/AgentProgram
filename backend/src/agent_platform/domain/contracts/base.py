from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


class FrozenContractModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        hide_input_in_errors=True,
    )


class VersionedContractModel(FrozenContractModel):
    schema_version: Literal[1]

    @field_validator("schema_version", mode="before")
    @classmethod
    def validate_schema_version(cls, value: object) -> int:
        if type(value) is not int:
            raise ValueError("schema version must be integer 1")
        return value
