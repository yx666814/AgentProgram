from typing import Protocol

from agent_platform.domain.contracts.role_cards import RoleCard
from agent_platform.domain.contracts.stages import Stage


class RoleCardRepository(Protocol):
    def load(self, stage: Stage, *, version: str) -> RoleCard: ...

    def load_all(self, *, version: str = "1.0.0") -> tuple[RoleCard, ...]: ...
