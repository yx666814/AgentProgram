import pytest

from agent_platform.domain.contracts import StageRunState
from agent_platform.domain.shared.errors import DomainError
from agent_platform.domain.workflows import require_stage_transition


def test_stage_transition_chain_and_recovery_edges_are_explicit() -> None:
    chain = (
        StageRunState.READY,
        StageRunState.DISCUSSING,
        StageRunState.PRODUCING,
        StageRunState.P2R_REVIEWING,
        StageRunState.QUALITY_CHECKING,
        StageRunState.WAITING_APPROVAL,
        StageRunState.HANDOFF_READY,
        StageRunState.COMPLETED,
    )
    for current, target in zip(chain[:-1], chain[1:], strict=True):
        require_stage_transition(current, target)

    require_stage_transition(StageRunState.NEEDS_FIX, StageRunState.PRODUCING)
    require_stage_transition(StageRunState.INTERRUPTED, StageRunState.DISCUSSING)


def test_locked_completed_and_skipped_stage_transitions_are_rejected() -> None:
    for current, target in (
        (StageRunState.LOCKED, StageRunState.READY),
        (StageRunState.READY, StageRunState.PRODUCING),
        (StageRunState.COMPLETED, StageRunState.DISCUSSING),
    ):
        with pytest.raises(DomainError, match="Stage run transition is not allowed"):
            require_stage_transition(current, target)
