from types import TracebackType
from typing import Protocol, Self

from agent_platform.domain.events.models import EventEnvelope


class EventRepository(Protocol):
    async def append(
        self,
        *,
        envelope: EventEnvelope,
        aggregate_type: str,
        aggregate_id: str,
    ) -> int: ...

    async def get(self, event_id: int) -> EventEnvelope | None: ...


class UnitOfWork(Protocol):
    @property
    def events(self) -> EventRepository: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
