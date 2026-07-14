import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import timedelta
from typing import Never

from fastapi import FastAPI
from sqlalchemy import text

from agent_platform.config.settings import Settings
from agent_platform.infrastructure.async_cleanup import await_cancellation_resistant
from agent_platform.infrastructure.database.session import Database, create_database
from agent_platform.infrastructure.logging.configure import LoggingRuntime, configure_logging
from agent_platform.infrastructure.redaction import SecretRegistration, register_known_secret
from agent_platform.infrastructure.workers.supervisor import WorkerSupervisor

_CLEANUP_FAILURE_NOTE = "Additional cleanup failure occurred."


async def _probe_database(database: Database) -> None:
    async with database.engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


def _add_cleanup_failure_note(primary_error: BaseException) -> None:
    original_cause = primary_error.__cause__
    original_context = primary_error.__context__
    original_suppress_context = primary_error.__suppress_context__
    try:
        BaseException.add_note(primary_error, _CLEANUP_FAILURE_NOTE)
    except BaseException:
        pass
    primary_error.__cause__ = original_cause
    primary_error.__context__ = original_context
    primary_error.__suppress_context__ = original_suppress_context


def _raise_primary_with_cleanup_failure(
    primary_error: BaseException,
    cleanup_error: BaseException,
) -> Never:
    del cleanup_error
    _add_cleanup_failure_note(primary_error)
    raise primary_error


async def _run_worker_watchdog(
    supervisor: WorkerSupervisor,
    interval_seconds: float,
) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        await supervisor.watch_once()


def _start_worker_watchdog(
    supervisor: WorkerSupervisor,
    interval_seconds: float,
) -> asyncio.Task[None]:
    return asyncio.create_task(_run_worker_watchdog(supervisor, interval_seconds))


async def _cancel_worker_watchdog(watchdog_task: asyncio.Task[None]) -> None:
    cancellation_requested_by_shutdown = (
        not watchdog_task.done() and watchdog_task.cancelling() == 0
    )
    if cancellation_requested_by_shutdown:
        watchdog_task.cancel()
    try:
        await watchdog_task
    except asyncio.CancelledError:
        if cancellation_requested_by_shutdown and watchdog_task.cancelled():
            return
        raise


async def _shutdown_resources(
    worker_watchdog_task: asyncio.Task[None] | None,
    worker_supervisor: WorkerSupervisor | None,
    database: Database | None,
    logging_runtime: LoggingRuntime | None,
    secret_registration: SecretRegistration | None,
) -> None:
    first_error: BaseException | None = None

    def remember_error(error: BaseException) -> None:
        nonlocal first_error
        if first_error is None:
            first_error = error
        else:
            _add_cleanup_failure_note(first_error)

    if worker_watchdog_task is not None:
        try:
            await _cancel_worker_watchdog(worker_watchdog_task)
        except BaseException as error:
            remember_error(error)
    if worker_supervisor is not None:
        try:
            await worker_supervisor.stop_all()
        except BaseException as error:
            remember_error(error)
    if database is not None:
        try:
            await database.dispose()
        except BaseException as error:
            remember_error(error)
    if logging_runtime is not None:
        try:
            logging_runtime.close()
        except BaseException as error:
            remember_error(error)
    if secret_registration is not None:
        try:
            secret_registration.close()
        except BaseException as error:
            remember_error(error)
    if first_error is not None:
        raise first_error


async def _await_cleanup_preserving_primary(
    cleanup: Awaitable[None],
    primary_error: BaseException,
) -> Never:
    cleanup_error: BaseException | None = None
    try:
        await await_cancellation_resistant(cleanup)
    except BaseException as error:
        cleanup_error = error
    if cleanup_error is not None:
        _raise_primary_with_cleanup_failure(primary_error, cleanup_error)
    raise primary_error


def _clear_resource_state(app: FastAPI) -> None:
    for attribute in (
        "worker_watchdog_task",
        "worker_supervisor",
        "database",
        "logging_runtime",
    ):
        if hasattr(app.state, attribute):
            delattr(app.state, attribute)


def build_lifespan(
    settings: Settings,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        secret_registration: SecretRegistration | None = None
        logging_runtime: LoggingRuntime | None = None
        database: Database | None = None
        worker_supervisor: WorkerSupervisor | None = None
        worker_watchdog_task: asyncio.Task[None] | None = None
        try:
            settings.ensure_directories()
            secret_registration = register_known_secret(settings.session_token)
            logging_runtime = configure_logging(
                settings.log_root,
                settings.log_level,
                max_bytes=settings.log_file_max_bytes,
                max_record_bytes=settings.log_record_max_bytes,
                retained_file_count=settings.log_file_retained_count,
                retention_age=settings.log_file_retention_age,
                queue_capacity=settings.log_queue_capacity,
                shutdown_drain_timeout=settings.log_shutdown_drain_timeout,
            )
            database = create_database(settings.database_path)
            await _probe_database(database)
            worker_supervisor = WorkerSupervisor(
                heartbeat_timeout=timedelta(seconds=settings.worker_heartbeat_timeout_seconds),
                ipc_replay_window_capacity=settings.worker_ipc_replay_window_capacity,
            )
            worker_watchdog_task = _start_worker_watchdog(
                worker_supervisor,
                settings.worker_watchdog_interval_seconds,
            )
            app.state.database = database
            app.state.worker_supervisor = worker_supervisor
            app.state.worker_watchdog_task = worker_watchdog_task
            app.state.logging_runtime = logging_runtime
        except BaseException as startup_error:
            try:
                await _await_cleanup_preserving_primary(
                    _shutdown_resources(
                        worker_watchdog_task,
                        worker_supervisor,
                        database,
                        logging_runtime,
                        secret_registration,
                    ),
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
                cleanup = _shutdown_resources(
                    worker_watchdog_task,
                    worker_supervisor,
                    database,
                    logging_runtime,
                    secret_registration,
                )
                if body_error is None:
                    await await_cancellation_resistant(cleanup)
                else:
                    await _await_cleanup_preserving_primary(cleanup, body_error)
            finally:
                _clear_resource_state(app)

    return lifespan
