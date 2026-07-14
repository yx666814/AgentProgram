from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_platform.domain.contracts.stages import Stage


class RoleCard(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    role_id: Stage
    stage_id: Stage
    display_name: Annotated[str, Field(min_length=1)]
    role_card_version: Annotated[
        str,
        Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$"),
    ]
    language: Literal["zh-CN"]
    content: Annotated[str, Field(min_length=1)]
    content_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

    @model_validator(mode="after")
    def role_must_match_stage(self) -> Self:
        if self.role_id is not self.stage_id:
            raise ValueError("role_id must match stage_id")
        return self
