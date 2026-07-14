import json

import pytest
from pydantic import ValidationError

from agent_platform.domain.contracts import (
    GLOBAL_RUNTIME_INVARIANTS,
    PRIMARY_MODEL_LIMIT,
    PROMPT_PRECEDENCE,
    SECONDARY_REVIEWER_LIMIT,
    CapabilityAccess,
    PromptLayer,
    RuntimeInvariant,
    Stage,
    StageContract,
    StagePathPolicy,
    StagePathScope,
    StageRunState,
)
from agent_platform.domain.shared.errors import DomainError, ErrorCategory


def test_stage_run_state_values_are_fixed() -> None:
    assert tuple(state.value for state in StageRunState) == (
        "locked",
        "ready",
        "discussing",
        "producing",
        "p2r_reviewing",
        "quality_checking",
        "waiting_approval",
        "handoff_ready",
        "completed",
        "warning_blocked",
        "needs_fix",
        "external_conflict",
        "interrupted",
        "failed",
        "cancelled",
        "abandoned",
    )


def test_prompt_precedence_is_not_reorderable() -> None:
    assert PROMPT_PRECEDENCE == (
        PromptLayer.GLOBAL_CORE_POLICY,
        PromptLayer.ROLE_CARD,
        PromptLayer.STAGE_CONTRACT,
        PromptLayer.MODEL_SUBROLE_PROMPT,
        PromptLayer.PROJECT_INSTRUCTIONS,
        PromptLayer.RUNTIME_STATE,
        PromptLayer.USER_MESSAGE,
        PromptLayer.PROJECT_FILE_CONTENT,
    )


def test_model_slot_limits_match_global_policy() -> None:
    assert PRIMARY_MODEL_LIMIT == 1
    assert SECONDARY_REVIEWER_LIMIT == 2


def test_global_runtime_invariants_are_complete_and_ordered() -> None:
    assert GLOBAL_RUNTIME_INVARIANTS == (
        RuntimeInvariant.ROOM_CONTEXT_ISOLATED,
        RuntimeInvariant.HANDOFF_REQUIRED_TO_UNLOCK,
        RuntimeInvariant.UPSTREAM_ARTIFACTS_IMMUTABLE,
        RuntimeInvariant.ONE_PRIMARY_TWO_REVIEWERS,
        RuntimeInvariant.PRIMARY_ONLY_TOOL_CALLS,
        RuntimeInvariant.DUAL_REVIEW_REQUIRED,
        RuntimeInvariant.DETERMINISTIC_QUALITY_GATE_REQUIRED,
        RuntimeInvariant.MANUAL_APPROVAL_BY_MODE,
        RuntimeInvariant.CAPABILITY_APPROVAL_ALWAYS_USER,
        RuntimeInvariant.TEMPORARY_GRANTS_TASK_SCOPED,
        RuntimeInvariant.FORBIDDEN_CAPABILITIES_NEVER_GRANTABLE,
        RuntimeInvariant.ORCHESTRATOR_ONLY_COMPLETION,
        RuntimeInvariant.CHAT_CONSENSUS_ARTIFACT_SEPARATED,
    )


def test_global_runtime_invariant_values_are_stable() -> None:
    assert tuple(invariant.value for invariant in RuntimeInvariant) == (
        "room_context_isolated",
        "handoff_required_to_unlock",
        "upstream_artifacts_immutable",
        "one_primary_two_reviewers",
        "primary_only_tool_calls",
        "dual_review_required",
        "deterministic_quality_gate_required",
        "manual_approval_by_mode",
        "capability_approval_always_user",
        "temporary_grants_task_scoped",
        "forbidden_capabilities_never_grantable",
        "orchestrator_only_completion",
        "chat_consensus_artifact_separated",
    )


def _path_policy() -> StagePathPolicy:
    return StagePathPolicy(
        read_scopes=(StagePathScope.PROJECT_NON_SENSITIVE,),
        write_scopes=(StagePathScope.PLANNER_ARTIFACT,),
        delete_scopes=(),
    )


def _stage_contract_data() -> dict[str, object]:
    return {
        "schema_version": 1,
        "contract_version": "1.0.0",
        "stage": Stage.PLANNER,
        "role_card_version": "1.0.0",
        "initial_state": StageRunState.READY,
        "default_capabilities": ("project.search",),
        "requestable_capabilities": ("shell.test",),
        "forbidden_capabilities": ("remote.deploy",),
        "path_policy": _path_policy(),
    }


def _stage_contract() -> StageContract:
    return StageContract(**_stage_contract_data())


def test_capability_access_values_are_stable() -> None:
    assert tuple(access.value for access in CapabilityAccess) == (
        "default",
        "requires_approval",
        "forbidden",
    )


def test_stage_path_scope_values_are_stable() -> None:
    assert tuple(scope.value for scope in StagePathScope) == (
        "project_non_sensitive",
        "planner_artifact",
        "designer_artifact",
        "builder_artifact",
        "reviewer_artifact",
        "deployer_artifact",
        "project_source",
        "project_test",
        "project_build_config",
        "generated",
        "deployment_config",
        "deployment_script",
        "stage_draft",
    )


def test_stage_contract_preserves_versioned_policy() -> None:
    contract = _stage_contract()

    assert contract.contract_version == "1.0.0"
    assert contract.stage is Stage.PLANNER
    assert contract.role_card_version == "1.0.0"
    assert contract.initial_state is StageRunState.READY
    assert contract.path_policy == _path_policy()


@pytest.mark.parametrize("field", ["contract_version", "role_card_version"])
@pytest.mark.parametrize("version", ["1", "1.0", "v1.0.0", "1.0.0-beta"])
def test_stage_contract_rejects_invalid_semantic_version(
    field: str,
    version: str,
) -> None:
    data = _stage_contract_data()
    data[field] = version

    with pytest.raises(ValidationError):
        StageContract.model_validate(data)


def test_stage_contract_parses_strict_wire_json() -> None:
    contract = StageContract.model_validate_json(
        json.dumps(
            {
                "schema_version": 1,
                "contract_version": "1.0.0",
                "stage": "builder",
                "role_card_version": "1.0.0",
                "initial_state": "locked",
                "default_capabilities": ["project.search"],
                "requestable_capabilities": ["shell.test"],
                "forbidden_capabilities": ["remote.deploy"],
                "path_policy": {
                    "read_scopes": ["project_non_sensitive"],
                    "write_scopes": ["builder_artifact", "stage_draft"],
                    "delete_scopes": ["stage_draft"],
                },
            }
        )
    )

    assert contract.stage is Stage.BUILDER
    assert contract.initial_state is StageRunState.LOCKED
    assert contract.path_policy.write_scopes == (
        StagePathScope.BUILDER_ARTIFACT,
        StagePathScope.STAGE_DRAFT,
    )


@pytest.mark.parametrize("field", ["read_scopes", "write_scopes", "delete_scopes"])
def test_stage_path_policy_rejects_duplicate_scopes(field: str) -> None:
    data = {
        "read_scopes": (StagePathScope.PROJECT_NON_SENSITIVE,),
        "write_scopes": (StagePathScope.PLANNER_ARTIFACT,),
        "delete_scopes": (),
    }
    data[field] = (StagePathScope.STAGE_DRAFT, StagePathScope.STAGE_DRAFT)

    with pytest.raises(ValidationError):
        StagePathPolicy.model_validate(data)


def test_stage_path_policy_rejects_delete_scope_outside_write_scope() -> None:
    with pytest.raises(ValidationError):
        StagePathPolicy(
            read_scopes=(StagePathScope.PROJECT_NON_SENSITIVE,),
            write_scopes=(StagePathScope.PLANNER_ARTIFACT,),
            delete_scopes=(StagePathScope.STAGE_DRAFT,),
        )


@pytest.mark.parametrize(
    ("field", "values"),
    [
        ("default_capabilities", ("project.search", "project.search")),
        ("requestable_capabilities", ("shell.test", "shell.test")),
        ("forbidden_capabilities", ("remote.deploy", "remote.deploy")),
    ],
)
def test_stage_contract_rejects_duplicate_capabilities(
    field: str,
    values: tuple[str, ...],
) -> None:
    data = _stage_contract_data()
    data[field] = values

    with pytest.raises(ValidationError):
        StageContract.model_validate(data)


@pytest.mark.parametrize("field", ["default_capabilities", "requestable_capabilities"])
def test_stage_contract_rejects_forbidden_capability_overlap(field: str) -> None:
    data = _stage_contract_data()
    data[field] = ("remote.deploy",)

    with pytest.raises(ValidationError):
        StageContract.model_validate(data)


def test_stage_contract_allows_default_capability_to_be_scope_requestable() -> None:
    data = _stage_contract_data()
    data["requestable_capabilities"] = ("project.search", "shell.test")

    contract = StageContract.model_validate(data)

    assert contract.capability_access("project.search") is CapabilityAccess.DEFAULT
    assert contract.can_request_capability("project.search") is True


def test_stage_contract_calculates_capability_access() -> None:
    contract = _stage_contract()

    assert contract.capability_access("project.search") is CapabilityAccess.DEFAULT
    assert contract.capability_access("shell.test") is CapabilityAccess.REQUIRES_APPROVAL
    assert contract.capability_access("remote.deploy") is CapabilityAccess.FORBIDDEN
    assert contract.capability_access("unknown.capability") is CapabilityAccess.FORBIDDEN
    assert contract.can_request_capability("shell.test") is True
    assert contract.can_request_capability("remote.deploy") is False
    assert contract.can_request_capability("unknown.capability") is False


def test_effective_capabilities_include_only_defaults_and_approved_requestable() -> None:
    contract = _stage_contract()

    assert contract.effective_capabilities() == frozenset({"project.search"})
    assert contract.effective_capabilities({"shell.test"}) == frozenset(
        {"project.search", "shell.test"}
    )


@pytest.mark.parametrize("capability", ["remote.deploy", "unknown.capability"])
def test_nonrequestable_capability_cannot_be_approved_without_leaking_value(
    capability: str,
) -> None:
    contract = _stage_contract()

    with pytest.raises(DomainError) as captured:
        contract.effective_capabilities({capability})

    assert captured.value.code == "stage_contract.capability_not_requestable"
    assert captured.value.category is ErrorCategory.PERMISSION
    assert captured.value.details == {"stage": "planner"}
    assert capability not in str(captured.value.args)


def test_stage_contract_models_are_frozen_and_forbid_extra_fields() -> None:
    contract = _stage_contract()

    with pytest.raises(ValidationError):
        contract.initial_state = StageRunState.LOCKED

    data = _stage_contract_data()
    data["unexpected"] = "value"
    with pytest.raises(ValidationError):
        StageContract.model_validate(data)
