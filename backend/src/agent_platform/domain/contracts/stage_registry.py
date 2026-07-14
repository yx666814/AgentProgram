from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from agent_platform.domain.contracts.runtime_policy import StageRunState
from agent_platform.domain.contracts.stage_contracts import (
    StageContract,
    StagePathPolicy,
    StagePathScope,
)
from agent_platform.domain.contracts.stages import STAGE_ORDER, Stage


def _contract(
    *,
    stage: Stage,
    initial_state: StageRunState,
    default_capabilities: tuple[str, ...],
    requestable_capabilities: tuple[str, ...],
    forbidden_capabilities: tuple[str, ...],
    path_policy: StagePathPolicy,
) -> StageContract:
    return StageContract(
        schema_version=1,
        contract_version="1.0.0",
        stage=stage,
        role_card_version="1.0.0",
        initial_state=initial_state,
        default_capabilities=default_capabilities,
        requestable_capabilities=requestable_capabilities,
        forbidden_capabilities=forbidden_capabilities,
        path_policy=path_policy,
    )


_PLANNER = _contract(
    stage=Stage.PLANNER,
    initial_state=StageRunState.READY,
    default_capabilities=(
        "project.inspect_structure",
        "project.search",
        "filesystem.read_project",
        "filesystem.read_reference",
        "filesystem.write_planner_artifact",
        "project.inspect_changes",
        "checkpoint.inspect_history",
        "artifact.create_draft",
        "artifact.update_planner_draft",
        "change_request.create",
    ),
    requestable_capabilities=(
        "filesystem.read_project",
        "filesystem.write_planner_artifact",
        "shell.run",
        "shell.test",
    ),
    forbidden_capabilities=(
        "filesystem.write_source",
        "filesystem.delete",
        "filesystem.write_outside_project",
        "shell.build",
        "dependency.install",
        "network.request",
        "remote.deploy",
        "credential.read",
        "system.modify",
    ),
    path_policy=StagePathPolicy(
        read_scopes=(
            StagePathScope.PROJECT_NON_SENSITIVE,
            StagePathScope.PLANNER_ARTIFACT,
            StagePathScope.STAGE_DRAFT,
        ),
        write_scopes=(
            StagePathScope.PLANNER_ARTIFACT,
            StagePathScope.STAGE_DRAFT,
        ),
        delete_scopes=(StagePathScope.STAGE_DRAFT,),
    ),
)

_DESIGNER = _contract(
    stage=Stage.DESIGNER,
    initial_state=StageRunState.LOCKED,
    default_capabilities=(
        "project.inspect_structure",
        "project.search",
        "filesystem.read_project",
        "filesystem.read_planner_artifact",
        "filesystem.write_designer_artifact",
        "project.inspect_changes",
        "checkpoint.inspect_history",
        "artifact.create_draft",
        "artifact.update_designer_draft",
        "change_request.create",
    ),
    requestable_capabilities=(
        "filesystem.read_project",
        "filesystem.write_designer_artifact",
        "shell.run",
        "shell.test",
        "dependency.inspect",
    ),
    forbidden_capabilities=(
        "filesystem.write_source",
        "filesystem.modify_planner_artifact",
        "filesystem.delete",
        "filesystem.write_outside_project",
        "shell.build",
        "dependency.install",
        "network.request",
        "remote.deploy",
        "credential.read",
        "system.modify",
    ),
    path_policy=StagePathPolicy(
        read_scopes=(
            StagePathScope.PROJECT_NON_SENSITIVE,
            StagePathScope.PLANNER_ARTIFACT,
            StagePathScope.DESIGNER_ARTIFACT,
            StagePathScope.STAGE_DRAFT,
        ),
        write_scopes=(
            StagePathScope.DESIGNER_ARTIFACT,
            StagePathScope.STAGE_DRAFT,
        ),
        delete_scopes=(StagePathScope.STAGE_DRAFT,),
    ),
)

_BUILDER = _contract(
    stage=Stage.BUILDER,
    initial_state=StageRunState.LOCKED,
    default_capabilities=(
        "project.inspect_structure",
        "project.search",
        "filesystem.read_project",
        "filesystem.write_source",
        "filesystem.write_test",
        "filesystem.write_build_config",
        "filesystem.write_builder_artifact",
        "filesystem.create_directory",
        "filesystem.delete_generated_or_builder_owned",
        "shell.run_project_command",
        "shell.build",
        "shell.test",
        "shell.lint",
        "shell.format",
        "dependency.inspect",
        "project.inspect_changes",
        "checkpoint.inspect_history",
        "checkpoint.create",
        "artifact.create_draft",
        "artifact.update_builder_draft",
        "change_request.create",
    ),
    requestable_capabilities=(
        "filesystem.write_source",
        "filesystem.write_test",
        "filesystem.write_build_config",
        "filesystem.write_builder_artifact",
        "shell.run_project_command",
        "dependency.install",
    ),
    forbidden_capabilities=(
        "filesystem.modify_planner_artifact",
        "filesystem.modify_designer_artifact",
        "filesystem.modify_reviewer_artifact",
        "filesystem.modify_deployer_artifact",
        "filesystem.write_outside_project",
        "remote.deploy",
        "system.modify",
        "credential.read",
    ),
    path_policy=StagePathPolicy(
        read_scopes=(
            StagePathScope.PROJECT_NON_SENSITIVE,
            StagePathScope.PLANNER_ARTIFACT,
            StagePathScope.DESIGNER_ARTIFACT,
            StagePathScope.BUILDER_ARTIFACT,
            StagePathScope.PROJECT_SOURCE,
            StagePathScope.PROJECT_TEST,
            StagePathScope.PROJECT_BUILD_CONFIG,
            StagePathScope.GENERATED,
            StagePathScope.STAGE_DRAFT,
        ),
        write_scopes=(
            StagePathScope.BUILDER_ARTIFACT,
            StagePathScope.PROJECT_SOURCE,
            StagePathScope.PROJECT_TEST,
            StagePathScope.PROJECT_BUILD_CONFIG,
            StagePathScope.GENERATED,
            StagePathScope.STAGE_DRAFT,
        ),
        delete_scopes=(
            StagePathScope.BUILDER_ARTIFACT,
            StagePathScope.PROJECT_SOURCE,
            StagePathScope.PROJECT_TEST,
            StagePathScope.GENERATED,
            StagePathScope.STAGE_DRAFT,
        ),
    ),
)

_REVIEWER = _contract(
    stage=Stage.REVIEWER,
    initial_state=StageRunState.LOCKED,
    default_capabilities=(
        "project.inspect_structure",
        "project.search",
        "filesystem.read_project",
        "filesystem.read_all_approved_artifacts",
        "filesystem.write_reviewer_artifact",
        "project.inspect_changes",
        "checkpoint.inspect_history",
        "shell.build",
        "shell.test",
        "shell.lint",
        "shell.typecheck",
        "shell.security_scan",
        "log.read_project",
        "artifact.create_draft",
        "artifact.update_reviewer_draft",
        "change_request.create",
    ),
    requestable_capabilities=(
        "filesystem.read_project",
        "shell.build",
        "shell.test",
        "shell.lint",
        "shell.typecheck",
        "shell.security_scan",
        "shell.run_project_command",
        "log.read_project",
    ),
    forbidden_capabilities=(
        "filesystem.write_source",
        "filesystem.modify_upstream_artifact",
        "filesystem.delete",
        "dependency.install",
        "checkpoint.restore",
        "remote.deploy",
        "credential.read",
    ),
    path_policy=StagePathPolicy(
        read_scopes=(
            StagePathScope.PROJECT_NON_SENSITIVE,
            StagePathScope.PLANNER_ARTIFACT,
            StagePathScope.DESIGNER_ARTIFACT,
            StagePathScope.BUILDER_ARTIFACT,
            StagePathScope.REVIEWER_ARTIFACT,
            StagePathScope.PROJECT_SOURCE,
            StagePathScope.PROJECT_TEST,
            StagePathScope.PROJECT_BUILD_CONFIG,
            StagePathScope.GENERATED,
            StagePathScope.STAGE_DRAFT,
        ),
        write_scopes=(
            StagePathScope.REVIEWER_ARTIFACT,
            StagePathScope.STAGE_DRAFT,
        ),
        delete_scopes=(StagePathScope.STAGE_DRAFT,),
    ),
)

_DEPLOYER = _contract(
    stage=Stage.DEPLOYER,
    initial_state=StageRunState.LOCKED,
    default_capabilities=(
        "project.inspect_structure",
        "project.search",
        "filesystem.read_project",
        "filesystem.read_all_approved_artifacts",
        "filesystem.write_deployment_document",
        "filesystem.write_deployment_config",
        "filesystem.write_deployment_script",
        "project.inspect_changes",
        "checkpoint.inspect_history",
        "artifact.create_draft",
        "artifact.update_deployer_draft",
        "change_request.create",
    ),
    requestable_capabilities=(
        "filesystem.read_project",
        "filesystem.write_deployment_document",
        "filesystem.write_deployment_config",
        "filesystem.write_deployment_script",
    ),
    forbidden_capabilities=(
        "shell.run",
        "shell.build",
        "shell.test",
        "docker.build",
        "package.build",
        "dependency.install",
        "checkpoint.restore",
        "remote.publish",
        "network.request",
        "remote.deploy",
        "credential.read",
        "filesystem.write_source",
    ),
    path_policy=StagePathPolicy(
        read_scopes=(
            StagePathScope.PROJECT_NON_SENSITIVE,
            StagePathScope.PLANNER_ARTIFACT,
            StagePathScope.DESIGNER_ARTIFACT,
            StagePathScope.BUILDER_ARTIFACT,
            StagePathScope.REVIEWER_ARTIFACT,
            StagePathScope.DEPLOYER_ARTIFACT,
            StagePathScope.PROJECT_SOURCE,
            StagePathScope.PROJECT_TEST,
            StagePathScope.PROJECT_BUILD_CONFIG,
            StagePathScope.GENERATED,
            StagePathScope.DEPLOYMENT_CONFIG,
            StagePathScope.DEPLOYMENT_SCRIPT,
            StagePathScope.STAGE_DRAFT,
        ),
        write_scopes=(
            StagePathScope.DEPLOYER_ARTIFACT,
            StagePathScope.DEPLOYMENT_CONFIG,
            StagePathScope.DEPLOYMENT_SCRIPT,
            StagePathScope.STAGE_DRAFT,
        ),
        delete_scopes=(StagePathScope.STAGE_DRAFT,),
    ),
)

_STAGE_CONTRACTS: Final[Mapping[Stage, StageContract]] = MappingProxyType(
    {
        Stage.PLANNER: _PLANNER,
        Stage.DESIGNER: _DESIGNER,
        Stage.BUILDER: _BUILDER,
        Stage.REVIEWER: _REVIEWER,
        Stage.DEPLOYER: _DEPLOYER,
    }
)


def get_stage_contract(stage: Stage) -> StageContract:
    return _STAGE_CONTRACTS[stage]


def load_stage_contracts() -> tuple[StageContract, ...]:
    return tuple(_STAGE_CONTRACTS[stage] for stage in STAGE_ORDER)
