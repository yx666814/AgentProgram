import asyncio
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
        self._active = False
        self._closed = False
        self._committed = False
        self.session: AsyncSession
        self.events: EventLogRepository
        self.outbox: OutboxRepository

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        if self._entered:
            raise RuntimeError("unit of work instances cannot be re-entered")

        self._entered = True
        self.session = self._session_factory(close_resets_only=False)
        self.events = EventLogRepository(self.session)
        self.outbox = OutboxRepository(self.session)
        self._active = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._active = False
        self._closed = True
        cleanup_task = asyncio.create_task(self._cleanup())
        cancellation: asyncio.CancelledError | None = None

        while not cleanup_task.done():
            try:
                await asyncio.shield(cleanup_task)
            except asyncio.CancelledError as current_cancellation:
                if cancellation is None:
                    cancellation = current_cancellation
            except BaseException:
                break

        try:
            cleanup_error = cleanup_task.exception()
        except asyncio.CancelledError as cleanup_cancellation:
            if cancellation is not None:
                raise cancellation from cleanup_cancellation
            raise

        if cleanup_error is not None:
            if cancellation is not None:
                raise cancellation from cleanup_error
            raise cleanup_error

        if cancellation is not None:
            raise cancellation

    async def commit(self) -> None:
        self._require_active()
        self._committed = False
        await self.session.commit()
        self._committed = True

    async def rollback(self) -> None:
        self._require_active()
        await self.session.rollback()
        self._committed = False

    def _require_active(self) -> None:
        if not self._active or self._closed:
            raise RuntimeError("unit of work is not active")

    async def _cleanup(self) -> None:
        try:
            if self.session.in_transaction():
                await self.session.rollback()
                self._committed = False
        finally:
            await self.session.close()
