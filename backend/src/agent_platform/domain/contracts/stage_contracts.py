from collections.abc import Collection
from enum import StrEnum
from typing import Self

from pydantic import model_validator

from agent_platform.domain.contracts.base import FrozenContractModel, VersionedContractModel
from agent_platform.domain.contracts.runtime_policy import StageRunState
from agent_platform.domain.contracts.scalars import ContractName, SemanticVersion
from agent_platform.domain.contracts.stages import Stage
from agent_platform.domain.shared.errors import DomainError, ErrorCategory


class CapabilityAccess(StrEnum):
    DEFAULT = "default"
    REQUIRES_APPROVAL = "requires_approval"
    FORBIDDEN = "forbidden"


class StagePathScope(StrEnum):
    PROJECT_NON_SENSITIVE = "project_non_sensitive"
    PLANNER_ARTIFACT = "planner_artifact"
    DESIGNER_ARTIFACT = "designer_artifact"
    BUILDER_ARTIFACT = "builder_artifact"
    REVIEWER_ARTIFACT = "reviewer_artifact"
    DEPLOYER_ARTIFACT = "deployer_artifact"
    PROJECT_SOURCE = "project_source"
    PROJECT_TEST = "project_test"
    PROJECT_BUILD_CONFIG = "project_build_config"
    GENERATED = "generated"
    DEPLOYMENT_CONFIG = "deployment_config"
    DEPLOYMENT_SCRIPT = "deployment_script"
    STAGE_DRAFT = "stage_draft"


class StagePathPolicy(FrozenContractModel):
    read_scopes: tuple[StagePathScope, ...]
    write_scopes: tuple[StagePathScope, ...]
    delete_scopes: tuple[StagePathScope, ...]

    @model_validator(mode="after")
    def validate_scopes(self) -> Self:
        for scopes in (self.read_scopes, self.write_scopes, self.delete_scopes):
            if len(scopes) != len(set(scopes)):
                raise ValueError("stage path scopes must be unique")
        if not set(self.delete_scopes).issubset(self.write_scopes):
            raise ValueError("delete scopes must be included in write scopes")
        return self


class StageContract(VersionedContractModel):
    contract_version: SemanticVersion
    stage: Stage
    role_card_version: SemanticVersion
    initial_state: StageRunState
    default_capabilities: tuple[ContractName, ...]
    requestable_capabilities: tuple[ContractName, ...]
    forbidden_capabilities: tuple[ContractName, ...]
    path_policy: StagePathPolicy

    @model_validator(mode="after")
    def validate_capabilities(self) -> Self:
        capability_groups = (
            self.default_capabilities,
            self.requestable_capabilities,
            self.forbidden_capabilities,
        )
        for capabilities in capability_groups:
            if len(capabilities) != len(set(capabilities)):
                raise ValueError("stage capabilities must be unique")
        forbidden = set(self.forbidden_capabilities)
        if forbidden.intersection(self.default_capabilities):
            raise ValueError("default capabilities cannot be forbidden")
        if forbidden.intersection(self.requestable_capabilities):
            raise ValueError("requestable capabilities cannot be forbidden")
        return self

    def capability_access(self, capability: str) -> CapabilityAccess:
        if capability in self.default_capabilities:
            return CapabilityAccess.DEFAULT
        if capability in self.requestable_capabilities:
            return CapabilityAccess.REQUIRES_APPROVAL
        return CapabilityAccess.FORBIDDEN

    def can_request_capability(self, capability: str) -> bool:
        return (
            capability in self.requestable_capabilities
            and capability not in self.forbidden_capabilities
        )

    def effective_capabilities(
        self,
        approved: Collection[str] = (),
    ) -> frozenset[str]:
        for capability in approved:
            if not self.can_request_capability(capability):
                raise DomainError(
                    code="stage_contract.capability_not_requestable",
                    message="Capability cannot be granted for this stage",
                    details={"stage": self.stage.value},
                    category=ErrorCategory.PERMISSION,
                )
        return frozenset(self.default_capabilities).union(approved)
