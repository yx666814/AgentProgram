import asyncio
import logging
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import timedelta
from typing import Never

from fastapi import FastAPI
from sqlalchemy import text

from agent_platform.application.events.outbox_dispatcher import OutboxDispatcher
from agent_platform.application.events.streaming import (
    EventStreamBroker,
    EventStreamService,
    EventTicketStore,
)
from agent_platform.application.governance import GovernanceApplicationService
from agent_platform.application.model_runtime import (
    AgentRunRegistry,
    AgentRuntimeService,
    ContextBuilder,
    ModelConfigurationService,
    PromptComposer,
    RollingSummaryBuilder,
)
from agent_platform.application.orchestration import OrchestrationApplicationService
from agent_platform.application.projects.service import ProjectApplicationService
from agent_platform.application.tooling import ToolApplicationService
from agent_platform.application.workflows import WorkflowApplicationService
from agent_platform.config.settings import Settings
from agent_platform.domain.shared.ids import new_id
from agent_platform.infrastructure.async_cleanup import await_cancellation_resistant
from agent_platform.infrastructure.database.instance_lock import ApplicationInstanceLock
from agent_platform.infrastructure.database.integrity import (
    IntegrityCheckMode,
    require_database_integrity,
)
from agent_platform.infrastructure.database.local_audit import LocalAuditPublisher
from agent_platform.infrastructure.database.maintenance import DatabaseMaintenance
from agent_platform.infrastructure.database.outbox_store import SqlAlchemyOutboxStore
from agent_platform.infrastructure.database.schema import CURRENT_DATABASE_REVISION
from agent_platform.infrastructure.database.session import Database, create_database
from agent_platform.infrastructure.events import WebSocketEventPublisher
from agent_platform.infrastructure.logging.configure import LoggingRuntime, configure_logging
from agent_platform.infrastructure.model_runtime import (
    AnthropicAdapter,
    DeterministicFakeModelAdapter,
    ModelOutputStore,
    OpenAICompatibleAdapter,
    UnavailableSecretStore,
)
from agent_platform.infrastructure.redaction import (
    SecretRegistration,
    redact_text,
    register_known_secret,
)
from agent_platform.infrastructure.resources.role_cards import PackageRoleCardLoader
from agent_platform.infrastructure.tooling import (
    AtomicFileTools,
    ControlledProcessRunner,
    PathGuard,
    ToolCatalog,
    ToolProcessRegistry,
)
from agent_platform.infrastructure.workers.supervisor import WorkerSupervisor
from agent_platform.ports.secrets import SecretStore

_CLEANUP_FAILURE_NOTE = "Additional cleanup failure occurred."
_LOGGER = logging.getLogger(__name__)


async def _probe_database(database: Database) -> None:
    async with database.engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def _database_schema_is_current(database: Database) -> bool:
    try:
        async with database.engine.connect() as connection:
            result = await connection.execute(text("SELECT version_num FROM alembic_version"))
            revision = str(result.scalar_one())
        return revision == CURRENT_DATABASE_REVISION
    except Exception:
        return False


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


async def _cancel_database_maintenance(maintenance_task: asyncio.Task[None]) -> None:
    cancellation_requested_by_shutdown = (
        not maintenance_task.done() and maintenance_task.cancelling() == 0
    )
    if cancellation_requested_by_shutdown:
        maintenance_task.cancel()
    try:
        await maintenance_task
    except asyncio.CancelledError:
        if cancellation_requested_by_shutdown and maintenance_task.cancelled():
            return
        raise


async def _stop_outbox_dispatcher(
    dispatcher: OutboxDispatcher,
    task: asyncio.Task[None],
    timeout_seconds: float,
) -> None:
    dispatcher.request_stop()
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout_seconds)
    except TimeoutError:
        requested = not task.done() and task.cancelling() == 0
        if requested:
            task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(task), 1.0)
        except asyncio.CancelledError:
            if requested and task.cancelled():
                return
            raise


async def _shutdown_resources(
    worker_watchdog_task: asyncio.Task[None] | None,
    worker_supervisor: WorkerSupervisor | None,
    tool_process_registry: ToolProcessRegistry | None,
    database_maintenance_task: asyncio.Task[None] | None,
    database_maintenance: DatabaseMaintenance | None,
    outbox_dispatcher: OutboxDispatcher | None,
    outbox_dispatcher_task: asyncio.Task[None] | None,
    outbox_shutdown_drain_seconds: float,
    database: Database | None,
    logging_runtime: LoggingRuntime | None,
    secret_registration: SecretRegistration | None,
    instance_lock: ApplicationInstanceLock | None,
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
    if tool_process_registry is not None:
        try:
            await tool_process_registry.cancel_all()
        except BaseException as error:
            remember_error(error)
    if worker_supervisor is not None:
        try:
            await worker_supervisor.stop_all()
        except BaseException as error:
            remember_error(error)
    if database_maintenance_task is not None:
        try:
            await _cancel_database_maintenance(database_maintenance_task)
        except BaseException as error:
            remember_error(error)
    if outbox_dispatcher is not None and outbox_dispatcher_task is not None:
        try:
            await _stop_outbox_dispatcher(
                outbox_dispatcher,
                outbox_dispatcher_task,
                outbox_shutdown_drain_seconds,
            )
        except BaseException as error:
            remember_error(error)
    if database_maintenance is not None:
        try:
            await database_maintenance.final_checkpoint()
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
    if instance_lock is not None:
        try:
            instance_lock.release()
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
        "tool_process_registry",
        "tool_service",
        "governance_service",
        "database",
        "project_service",
        "workflow_service",
        "event_stream_service",
        "event_stream_broker",
        "event_ticket_store",
        "model_configuration_service",
        "agent_runtime_service",
        "agent_run_registry",
        "orchestration_service",
        "secret_store",
        "logging_runtime",
        "database_maintenance",
        "database_maintenance_task",
        "instance_lock",
        "outbox_dispatcher",
        "outbox_dispatcher_task",
    ):
        if hasattr(app.state, attribute):
            delattr(app.state, attribute)


def build_lifespan(
    settings: Settings,
    secret_store: SecretStore | None = None,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    resolved_secret_store = secret_store or UnavailableSecretStore()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        instance_lock: ApplicationInstanceLock | None = None
        secret_registration: SecretRegistration | None = None
        logging_runtime: LoggingRuntime | None = None
        database: Database | None = None
        worker_supervisor: WorkerSupervisor | None = None
        tool_process_registry: ToolProcessRegistry | None = None
        worker_watchdog_task: asyncio.Task[None] | None = None
        database_maintenance: DatabaseMaintenance | None = None
        database_maintenance_task: asyncio.Task[None] | None = None
        outbox_dispatcher: OutboxDispatcher | None = None
        outbox_dispatcher_task: asyncio.Task[None] | None = None
        try:
            settings.ensure_directories()
            instance_lock = ApplicationInstanceLock.acquire(settings.runtime_root)
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
            await require_database_integrity(
                settings.database_path,
                IntegrityCheckMode.QUICK,
                settings.database_operation_timeout_seconds,
            )
            worker_supervisor = WorkerSupervisor(
                heartbeat_timeout=timedelta(seconds=settings.worker_heartbeat_timeout_seconds),
                ipc_replay_window_capacity=settings.worker_ipc_replay_window_capacity,
            )
            worker_watchdog_task = _start_worker_watchdog(
                worker_supervisor,
                settings.worker_watchdog_interval_seconds,
            )
            database_maintenance = DatabaseMaintenance(
                database_path=settings.database_path,
                backup_root=settings.backup_root,
                log_root=settings.log_root,
                operation_timeout_seconds=settings.database_operation_timeout_seconds,
                maintenance_interval_seconds=settings.database_maintenance_interval_seconds,
                integrity_interval_seconds=settings.database_integrity_check_interval_seconds,
                backup_interval_seconds=settings.database_backup_interval_seconds,
                backup_retain_count=settings.database_backup_retained_count,
                backup_retention_age=settings.database_backup_retention_age,
                log_retention_age=settings.log_file_retention_age,
                max_entries_per_run=settings.database_maintenance_max_entries_per_run,
                size_warning_bytes=settings.database_size_warning_bytes,
            )
            database_maintenance_task = asyncio.create_task(database_maintenance.run_forever())
            event_stream_broker = EventStreamBroker(
                queue_capacity=settings.websocket_subscriber_queue_capacity,
                dedup_capacity=settings.websocket_publisher_dedup_capacity,
            )
            event_ticket_store = EventTicketStore(
                timedelta(seconds=settings.websocket_ticket_ttl_seconds)
            )
            event_stream_service = EventStreamService(
                database,
                event_ticket_store,
                event_stream_broker,
                replay_batch_size=settings.websocket_replay_batch_size,
            )
            agent_run_registry = AgentRunRegistry()
            tool_catalog = ToolCatalog()
            path_guard = PathGuard()
            file_tools = AtomicFileTools(max_file_bytes=settings.tool_file_max_bytes)
            tool_process_registry = ToolProcessRegistry()
            process_runner = ControlledProcessRunner(
                tool_process_registry,
                max_output_bytes=settings.tool_output_max_bytes,
            )
            model_output_store = ModelOutputStore(
                settings.model_output_root,
                max_output_bytes=settings.model_output_max_bytes,
            )
            model_output_store.initialize()
            model_configuration_service = ModelConfigurationService(database)
            agent_runtime_service = AgentRuntimeService(
                database,
                settings,
                resolved_secret_store,
                (
                    OpenAICompatibleAdapter(timeout_seconds=settings.model_http_timeout_seconds),
                    AnthropicAdapter(timeout_seconds=settings.model_http_timeout_seconds),
                    DeterministicFakeModelAdapter(),
                ),
                model_output_store,
                PromptComposer(PackageRoleCardLoader()),
                ContextBuilder(max_characters=settings.model_context_max_characters),
                RollingSummaryBuilder(
                    trigger_characters=settings.model_summary_trigger_characters,
                    max_summary_characters=settings.model_summary_max_characters,
                ),
                agent_run_registry,
            )
            workflow_service = WorkflowApplicationService(database)
            tool_service = ToolApplicationService(
                database,
                settings,
                tool_catalog,
                path_guard,
                file_tools,
                process_runner,
                tool_process_registry,
            )
            governance_service = GovernanceApplicationService(
                database,
                settings,
                file_tools,
                agent_run_registry,
                tool_process_registry,
                worker_supervisor,
            )
            orchestration_service = OrchestrationApplicationService(
                database,
                settings,
                workflow_service,
                agent_runtime_service,
                tool_service,
                governance_service,
                tool_catalog,
                file_tools,
            )
            if await _database_schema_is_current(database):
                await governance_service.recover_incomplete_workflows()
            if hasattr(database, "sessions"):
                database_write_lock: asyncio.Lock | None = getattr(
                    database,
                    "write_lock",
                    None,
                )
                outbox_store = SqlAlchemyOutboxStore(
                    database.sessions,
                    lease_owner=new_id("dispatcher"),
                    lease_seconds=settings.outbox_lease_seconds,
                    max_attempts=settings.outbox_max_attempts,
                    backoff_base_seconds=settings.outbox_backoff_base_seconds,
                    backoff_max_seconds=settings.outbox_backoff_max_seconds,
                    recovery_batch_size=settings.outbox_recovery_batch_size,
                    write_lock=database_write_lock,
                )
                outbox_dispatcher = OutboxDispatcher(
                    store=outbox_store,
                    publishers=(
                        LocalAuditPublisher(database.sessions, database_write_lock),
                        WebSocketEventPublisher(event_stream_broker),
                    ),
                    poll_interval_seconds=settings.outbox_poll_interval_seconds,
                    publish_timeout_seconds=settings.outbox_publish_timeout_seconds,
                    cleanup_interval_seconds=settings.outbox_cleanup_interval_seconds,
                    delivered_retention=settings.outbox_delivered_retention_age,
                    cleanup_batch_size=settings.outbox_cleanup_batch_size,
                )
                outbox_dispatcher_task = asyncio.create_task(outbox_dispatcher.run())
            app.state.database = database
            app.state.project_service = ProjectApplicationService(database, settings)
            app.state.workflow_service = workflow_service
            app.state.event_stream_broker = event_stream_broker
            app.state.event_ticket_store = event_ticket_store
            app.state.event_stream_service = event_stream_service
            app.state.model_configuration_service = model_configuration_service
            app.state.agent_runtime_service = agent_runtime_service
            app.state.agent_run_registry = agent_run_registry
            app.state.tool_process_registry = tool_process_registry
            app.state.tool_service = tool_service
            app.state.governance_service = governance_service
            app.state.orchestration_service = orchestration_service
            app.state.secret_store = resolved_secret_store
            app.state.worker_supervisor = worker_supervisor
            app.state.worker_watchdog_task = worker_watchdog_task
            app.state.logging_runtime = logging_runtime
            app.state.database_maintenance = database_maintenance
            app.state.database_maintenance_task = database_maintenance_task
            app.state.instance_lock = instance_lock
            if outbox_dispatcher is not None and outbox_dispatcher_task is not None:
                app.state.outbox_dispatcher = outbox_dispatcher
                app.state.outbox_dispatcher_task = outbox_dispatcher_task
        except BaseException as startup_error:
            _LOGGER.exception("Application startup failed")
            sys.stderr.write(
                "AGENT_PLATFORM_STARTUP_ERROR "
                f"{type(startup_error).__name__}: {redact_text(str(startup_error))}\n"
            )
            sys.stderr.flush()
            try:
                await _await_cleanup_preserving_primary(
                    _shutdown_resources(
                        worker_watchdog_task,
                        worker_supervisor,
                        tool_process_registry,
                        database_maintenance_task,
                        database_maintenance,
                        outbox_dispatcher,
                        outbox_dispatcher_task,
                        settings.outbox_shutdown_drain_seconds,
                        database,
                        logging_runtime,
                        secret_registration,
                        instance_lock,
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
                    tool_process_registry,
                    database_maintenance_task,
                    database_maintenance,
                    outbox_dispatcher,
                    outbox_dispatcher_task,
                    settings.outbox_shutdown_drain_seconds,
                    database,
                    logging_runtime,
                    secret_registration,
                    instance_lock,
                )
                if body_error is None:
                    await await_cancellation_resistant(cleanup)
                else:
                    await _await_cleanup_preserving_primary(cleanup, body_error)
            finally:
                _clear_resource_state(app)

    return lifespan
