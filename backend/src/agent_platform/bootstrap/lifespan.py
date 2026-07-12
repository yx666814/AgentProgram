from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import timedelta
from typing import Never

from fastapi import FastAPI
from sqlalchemy import text

from agent_platform.config.settings import Settings
from agent_platform.infrastructure.async_cleanup import await_cancellation_resistant
from agent_platform.infrastructure.database.session import Database, create_database
from agent_platform.infrastructure.logging.configure import configure_logging
from agent_platform.infrastructure.workers.supervisor import WorkerSupervisor


async def _probe_database(database: Database) -> None:
    async with database.engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def _shutdown_resources(
    worker_supervisor: WorkerSupervisor,
    database: Database,
) -> None:
    try:
        await worker_supervisor.stop_all()
    except BaseException as stop_error:
        try:
            await database.dispose()
        except BaseException as dispose_error:
            raise stop_error from dispose_error
        raise
    else:
        await database.dispose()


async def _await_cleanup_preserving_primary(
    cleanup: Awaitable[None],
    primary_error: BaseException,
) -> Never:
    try:
        await await_cancellation_resistant(cleanup)
    except BaseException as cleanup_error:
        raise primary_error from cleanup_error
    raise primary_error


def _clear_resource_state(app: FastAPI) -> None:
    for attribute in ("worker_supervisor", "database"):
        if hasattr(app.state, attribute):
            delattr(app.state, attribute)


def build_lifespan(
    settings: Settings,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.ensure_directories()
        configure_logging(settings.log_root, settings.log_level)
        database = create_database(settings.database_path)
        try:
            await _probe_database(database)
            worker_supervisor = WorkerSupervisor(
                heartbeat_timeout=timedelta(seconds=settings.worker_heartbeat_timeout_seconds)
            )
            app.state.database = database
            app.state.worker_supervisor = worker_supervisor
        except BaseException as startup_error:
            try:
                await _await_cleanup_preserving_primary(
                    database.dispose(),
                    startup_error,
                )
            finally:
                _clear_resource_state(app)
        body_error: BaseException | None = None
        try:
            yield
        except BaseException as error:
            body_error = error
        finally:
            try:
                cleanup = _shutdown_resources(worker_supervisor, database)
                if body_error is None:
                    await await_cancellation_resistant(cleanup)
                else:
                    await _await_cleanup_preserving_primary(cleanup, body_error)
            finally:
                _clear_resource_state(app)

    return lifespan
