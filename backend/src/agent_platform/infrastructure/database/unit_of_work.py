import asyncio
from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent_platform.infrastructure.async_cleanup import await_cancellation_resistant
from agent_platform.infrastructure.database.project_repository import (
    SqlAlchemyProjectRepository,
)
from agent_platform.infrastructure.database.repositories import EventLogRepository
from agent_platform.ports.event_publishing import LOCAL_AUDIT_CONSUMER


class SqlAlchemyUnitOfWork:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        delivery_targets: tuple[str, ...] = (LOCAL_AUDIT_CONSUMER,),
        *,
        write: bool = False,
        write_lock: asyncio.Lock | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._delivery_targets = delivery_targets
        self._write = write
        self._write_lock = write_lock
        self._write_lock_acquired = False
        self._entered = False
        self._active = False
        self._closed = False
        self._committed = False
        self.session: AsyncSession
        self.events: EventLogRepository
        self.projects: SqlAlchemyProjectRepository

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        if self._entered:
            raise RuntimeError("unit of work instances cannot be re-entered")

        self._entered = True
        if self._write and self._write_lock is not None:
            await self._write_lock.acquire()
            self._write_lock_acquired = True
        try:
            self.session = self._session_factory(close_resets_only=False)
            self.events = EventLogRepository(self.session, self._delivery_targets)
            self.projects = SqlAlchemyProjectRepository(self.session)
        except BaseException:
            if self._write_lock_acquired and self._write_lock is not None:
                self._write_lock.release()
                self._write_lock_acquired = False
            raise
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
        await await_cancellation_resistant(self._cleanup())

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
            try:
                await self.session.close()
            finally:
                if self._write_lock_acquired and self._write_lock is not None:
                    self._write_lock.release()
                    self._write_lock_acquired = False
