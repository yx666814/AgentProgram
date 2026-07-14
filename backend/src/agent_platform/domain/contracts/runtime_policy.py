from enum import StrEnum
from typing import Final


class StageRunState(StrEnum):
    LOCKED = "locked"
    READY = "ready"
    DISCUSSING = "discussing"
    PRODUCING = "producing"
    P2R_REVIEWING = "p2r_reviewing"
    QUALITY_CHECKING = "quality_checking"
    WAITING_APPROVAL = "waiting_approval"
    HANDOFF_READY = "handoff_ready"
    COMPLETED = "completed"
    WARNING_BLOCKED = "warning_blocked"
    NEEDS_FIX = "needs_fix"
    EXTERNAL_CONFLICT = "external_conflict"
    INTERRUPTED = "interrupted"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ABANDONED = "abandoned"


class PromptLayer(StrEnum):
    GLOBAL_CORE_POLICY = "global_core_policy"
    ROLE_CARD = "role_card"
    STAGE_CONTRACT = "stage_contract"
    MODEL_SUBROLE_PROMPT = "model_subrole_prompt"
    PROJECT_INSTRUCTIONS = "project_instructions"
    RUNTIME_STATE = "runtime_state"
    USER_MESSAGE = "user_message"
    PROJECT_FILE_CONTENT = "project_file_content"


class RuntimeInvariant(StrEnum):
    ROOM_CONTEXT_ISOLATED = "room_context_isolated"
    HANDOFF_REQUIRED_TO_UNLOCK = "handoff_required_to_unlock"
    UPSTREAM_ARTIFACTS_IMMUTABLE = "upstream_artifacts_immutable"
    ONE_PRIMARY_TWO_REVIEWERS = "one_primary_two_reviewers"
    PRIMARY_ONLY_TOOL_CALLS = "primary_only_tool_calls"
    DUAL_REVIEW_REQUIRED = "dual_review_required"
    DETERMINISTIC_QUALITY_GATE_REQUIRED = "deterministic_quality_gate_required"
    MANUAL_APPROVAL_BY_MODE = "manual_approval_by_mode"
    CAPABILITY_APPROVAL_ALWAYS_USER = "capability_approval_always_user"
    TEMPORARY_GRANTS_TASK_SCOPED = "temporary_grants_task_scoped"
    FORBIDDEN_CAPABILITIES_NEVER_GRANTABLE = "forbidden_capabilities_never_grantable"
    ORCHESTRATOR_ONLY_COMPLETION = "orchestrator_only_completion"
    CHAT_CONSENSUS_ARTIFACT_SEPARATED = "chat_consensus_artifact_separated"


PROMPT_PRECEDENCE: Final[tuple[PromptLayer, ...]] = tuple(PromptLayer)
GLOBAL_RUNTIME_INVARIANTS: Final[tuple[RuntimeInvariant, ...]] = tuple(RuntimeInvariant)
PRIMARY_MODEL_LIMIT: Final[int] = 1
SECONDARY_REVIEWER_LIMIT: Final[int] = 2
