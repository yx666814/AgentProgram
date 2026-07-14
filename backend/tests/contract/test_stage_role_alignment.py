import re

import pytest

from agent_platform.domain.contracts import (
    STAGE_ORDER,
    CapabilityAccess,
    Stage,
    StagePathPolicy,
    StagePathScope,
    StageRunState,
    get_stage_contract,
    load_stage_contracts,
)
from agent_platform.infrastructure.resources.role_cards import PackageRoleCardLoader

EXPECTED_DEFAULT_COUNTS = {
    Stage.PLANNER: 10,
    Stage.DESIGNER: 10,
    Stage.BUILDER: 21,
    Stage.REVIEWER: 16,
    Stage.DEPLOYER: 12,
}


def _extract_default_capabilities(content: str) -> tuple[str, ...]:
    pattern = re.compile(
        r"## 9\. 默认能力\s+.*?Primary 默认拥有：\s+```text\r?\n"
        r"(?P<body>.*?)\r?\n```",
        flags=re.DOTALL,
    )
    matches = list(pattern.finditer(content))
    if len(matches) != 1:
        raise AssertionError("role card must contain exactly one default capability block")
    capabilities = tuple(
        line.strip() for line in matches[0].group("body").splitlines() if line.strip()
    )
    if not capabilities:
        raise AssertionError("role card default capability block must not be empty")
    return capabilities


def test_stage_contract_registry_preserves_fixed_stage_order() -> None:
    contracts = load_stage_contracts()

    assert len(contracts) == 5
    assert tuple(contract.stage for contract in contracts) == STAGE_ORDER
    assert tuple(get_stage_contract(stage) for stage in STAGE_ORDER) == contracts


@pytest.mark.parametrize("stage", STAGE_ORDER)
def test_stage_contract_matches_packaged_role_card_defaults(stage: Stage) -> None:
    contract = get_stage_contract(stage)
    role_card = PackageRoleCardLoader().load(stage, version=contract.role_card_version)

    assert contract.schema_version == 1
    assert contract.contract_version == "1.0.0"
    assert contract.role_card_version == "1.0.0"
    assert contract.default_capabilities == _extract_default_capabilities(role_card.content)
    assert len(contract.default_capabilities) == EXPECTED_DEFAULT_COUNTS[stage]
    assert len(contract.default_capabilities) == len(set(contract.default_capabilities))


def test_stage_contract_initial_states_follow_unlock_order() -> None:
    assert get_stage_contract(Stage.PLANNER).initial_state is StageRunState.READY
    for stage in STAGE_ORDER[1:]:
        assert get_stage_contract(stage).initial_state is StageRunState.LOCKED


def test_representative_capability_boundaries_match_role_rules() -> None:
    planner = get_stage_contract(Stage.PLANNER)
    builder = get_stage_contract(Stage.BUILDER)
    reviewer = get_stage_contract(Stage.REVIEWER)
    deployer = get_stage_contract(Stage.DEPLOYER)

    assert planner.capability_access("shell.test") is CapabilityAccess.REQUIRES_APPROVAL
    assert planner.capability_access("filesystem.write_source") is CapabilityAccess.FORBIDDEN
    assert builder.can_request_capability("dependency.install") is True
    assert builder.can_request_capability("remote.deploy") is False
    assert reviewer.capability_access("filesystem.write_source") is CapabilityAccess.FORBIDDEN
    assert deployer.can_request_capability("shell.run") is False
    assert deployer.can_request_capability("shell.test") is False


EXPECTED_PATH_POLICIES = {
    Stage.PLANNER: StagePathPolicy(
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
    Stage.DESIGNER: StagePathPolicy(
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
    Stage.BUILDER: StagePathPolicy(
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
    Stage.REVIEWER: StagePathPolicy(
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
    Stage.DEPLOYER: StagePathPolicy(
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
}


@pytest.mark.parametrize("stage", STAGE_ORDER)
def test_stage_contract_path_policy_matches_stage_ownership(stage: Stage) -> None:
    assert get_stage_contract(stage).path_policy == EXPECTED_PATH_POLICIES[stage]
