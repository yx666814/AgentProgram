from __future__ import annotations

from typing import Final

from agent_platform.domain.contracts import StageRunState
from agent_platform.domain.shared.errors import DomainError, ErrorCategory

_ALLOWED_TRANSITIONS: Final[dict[StageRunState, frozenset[StageRunState]]] = {
    StageRunState.READY: frozenset({StageRunState.DISCUSSING}),
    StageRunState.DISCUSSING: frozenset({StageRunState.PRODUCING}),
    StageRunState.PRODUCING: frozenset({StageRunState.P2R_REVIEWING}),
    StageRunState.P2R_REVIEWING: frozenset({StageRunState.QUALITY_CHECKING}),
    StageRunState.QUALITY_CHECKING: frozenset({StageRunState.WAITING_APPROVAL}),
    StageRunState.WAITING_APPROVAL: frozenset({StageRunState.HANDOFF_READY}),
    StageRunState.HANDOFF_READY: frozenset({StageRunState.COMPLETED}),
    StageRunState.NEEDS_FIX: frozenset({StageRunState.PRODUCING}),
    StageRunState.WARNING_BLOCKED: frozenset({StageRunState.DISCUSSING}),
    StageRunState.EXTERNAL_CONFLICT: frozenset({StageRunState.DISCUSSING}),
    StageRunState.INTERRUPTED: frozenset({StageRunState.DISCUSSING}),
}

_CANCELLABLE_STATES: Final[frozenset[StageRunState]] = frozenset(
    {
        StageRunState.READY,
        StageRunState.DISCUSSING,
        StageRunState.PRODUCING,
        StageRunState.P2R_REVIEWING,
        StageRunState.QUALITY_CHECKING,
        StageRunState.WAITING_APPROVAL,
        StageRunState.HANDOFF_READY,
        StageRunState.WARNING_BLOCKED,
        StageRunState.NEEDS_FIX,
        StageRunState.EXTERNAL_CONFLICT,
        StageRunState.INTERRUPTED,
    }
)


def require_stage_transition(current: StageRunState, target: StageRunState) -> None:
    allowed = _ALLOWED_TRANSITIONS.get(current, frozenset())
    if target in allowed:
        return
    if (
        target
        in {
            StageRunState.FAILED,
            StageRunState.CANCELLED,
            StageRunState.ABANDONED,
        }
        and current in _CANCELLABLE_STATES
    ):
        return
    raise DomainError(
        code="stage_run.invalid_transition",
        message="Stage run transition is not allowed",
        category=ErrorCategory.CONFLICT,
        details={"current_state": current.value, "target_state": target.value},
    )
