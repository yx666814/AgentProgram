from agent_platform.domain.contracts import (
    GLOBAL_RUNTIME_INVARIANTS,
    PRIMARY_MODEL_LIMIT,
    PROMPT_PRECEDENCE,
    SECONDARY_REVIEWER_LIMIT,
    PromptLayer,
    RuntimeInvariant,
    StageRunState,
)


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
