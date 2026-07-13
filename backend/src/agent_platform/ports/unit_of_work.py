from datetime import datetime
from types import TracebackType
from typing import Protocol, Self


class EventRepository(Protocol):
    async def append(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, object],
        occurred_at: datetime,
        project_id: str | None = None,
        workflow_id: str | None = None,
        room_id: str | None = None,
        task_id: str | None = None,
    ) -> int: ...


class OutboxRepository(Protocol):
    async def enqueue(self, event_id: int) -> str: ...


class UnitOfWork(Protocol):
    @property
    def events(self) -> EventRepository: ...

    @property
    def outbox(self) -> OutboxRepository: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
