from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent_platform.infrastructure.database.repositories import (
    EventLogRepository,
    OutboxRepository,
)


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._entered = False
        self._committed = False
        self.session: AsyncSession
        self.events: EventLogRepository
        self.outbox: OutboxRepository

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        if self._entered:
            raise RuntimeError("unit of work instances cannot be re-entered")

        self._entered = True
        self.session = self._session_factory()
        self.events = EventLogRepository(self.session)
        self.outbox = OutboxRepository(self.session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            if exc_type is not None or not self._committed:
                await self.rollback()
        finally:
            await self.session.close()

    async def commit(self) -> None:
        self._committed = False
        await self.session.commit()
        self._committed = True

    async def rollback(self) -> None:
        await self.session.rollback()
        self._committed = False
