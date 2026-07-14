from typing import Annotated, Literal

from pydantic import Field

from agent_platform.domain.contracts.base import FrozenContractModel, VersionedContractModel
from agent_platform.domain.contracts.scalars import ContractId, PositiveVersion
from agent_platform.domain.contracts.stages import Stage


class ContentHash(FrozenContractModel):
    algorithm: Literal["sha256"] = "sha256"
    digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class ProjectCheckpointRef(VersionedContractModel):
    project_id: ContractId
    checkpoint_id: ContractId
    content_hash: ContentHash


class ArtifactRef(VersionedContractModel):
    project_id: ContractId
    artifact_id: ContractId
    stage: Stage
    version: PositiveVersion
    content_hash: ContentHash
