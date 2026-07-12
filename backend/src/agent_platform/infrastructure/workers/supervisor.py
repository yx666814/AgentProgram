import asyncio
import os
import signal
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import psutil  # type: ignore[import-untyped]

from agent_platform.domain.shared.ids import new_id
from agent_platform.infrastructure.async_cleanup import await_cancellation_resistant
from agent_platform.interfaces.ipc.framing import FrameDecoder, FramingError, encode_frame
from agent_platform.interfaces.ipc.messages import IpcMessage, MessageType

from .windows_job import WindowsJob, WindowsStartGate

_WINDOWS_START_GATE_TIMEOUT_SECONDS = 5.0
_SECONDARY_CLEANUP_FAILURE_NOTE = "Additional worker cleanup failure occurred."
_POSIX_GROUP_TERM_TIMEOUT_SECONDS = 0.5
_POSIX_GROUP_KILL_TIMEOUT_SECONDS = 0.5
_PIPE_CLOSE_TIMEOUT_SECONDS = 0.5


class WorkerError(RuntimeError):
    """Base class for sanitized worker lifecycle errors."""


class WorkerUnavailableError(WorkerError):
    """Raised when a worker can no longer accept or answer messages."""


class WorkerProtocolError(WorkerUnavailableError):
    """Raised when a worker writes invalid IPC output."""


class WorkerTimeoutError(WorkerError):
    """Raised when a worker does not answer within the response deadline."""


def _add_secondary_cleanup_note(primary_error: BaseException) -> None:
    """Best-effort redacted reporting for cleanup failures after the primary error."""

    original_cause = primary_error.__cause__
    original_context = primary_error.__context__
    original_suppress_context = primary_error.__suppress_context__
    try:
        BaseException.add_note(primary_error, _SECONDARY_CLEANUP_FAILURE_NOTE)
    except BaseException:
        return
    try:
        primary_error.__cause__ = original_cause
        primary_error.__context__ = original_context
        primary_error.__suppress_context__ = original_suppress_context
    except BaseException:
        pass


def _terminate_psutil_processes(processes: list[Any]) -> None:
    for process in processes:
        try:
            process.terminate()
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            pass
    if not processes:
        return
    _, alive = psutil.wait_procs(processes, timeout=0.5)
    survivors = cast(list[Any], alive)
    for process in survivors:
        try:
            process.kill()
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            pass
    if survivors:
        psutil.wait_procs(survivors, timeout=0.5)


def _terminate_process_tree_sync(pid: int) -> None:
    try:
        parent = psutil.Process(pid)
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
        return
    try:
        children = cast(list[Any], parent.children(recursive=True))
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
        children = []
    _terminate_psutil_processes(children)
    try:
        remaining_children = cast(list[Any], parent.children(recursive=True))
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
        remaining_children = []
    _terminate_psutil_processes(remaining_children)
    _terminate_psutil_processes([parent])


def _capture_descendants_sync(pid: int) -> list[Any]:
    try:
        parent = psutil.Process(pid)
        return cast(list[Any], parent.children(recursive=True))
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
        return []


@dataclass
class WorkerHandle:
    worker_id: str
    project_id: str
    process: asyncio.subprocess.Process
    decoder: FrameDecoder
    outbound_sequence: int
    last_heartbeat_at: datetime
    pending: dict[str, asyncio.Future[IpcMessage]]
    process_group_id: int | None
    job: WindowsJob | None = field(default=None, repr=False)
    last_inbound_sequence: int = 0
    seen_inbound_message_ids: set[str] = field(default_factory=set, repr=False)
    reader_task: asyncio.Task[None] = field(init=False, repr=False)
    _stderr_task: asyncio.Task[None] = field(init=False, repr=False)
    _write_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _state_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _stopping: bool = field(default=False, repr=False)
    _stop_task: asyncio.Task[None] | None = field(default=None, repr=False)
    _pending_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    _stopping_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)


class WorkerSupervisor:
    def __init__(
        self,
        heartbeat_timeout: timedelta,
        *,
        response_timeout_seconds: float = 5.0,
        shutdown_timeout_seconds: float = 3.0,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._heartbeat_timeout = heartbeat_timeout
        self._response_timeout_seconds = response_timeout_seconds
        self._shutdown_timeout_seconds = min(shutdown_timeout_seconds, 3.0)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._workers: dict[str, WorkerHandle] = {}
        self._projects: dict[str, WorkerHandle] = {}
        self._registry_lock = asyncio.Lock()
        self._closing = False

    async def start(
        self,
        project_id: str,
        worker_module: str = "agent_platform.workers.main",
    ) -> WorkerHandle:
        if not project_id or not project_id.isascii() or not project_id.isprintable():
            raise ValueError("invalid project id")
        async with self._registry_lock:
            if self._closing:
                raise WorkerUnavailableError("worker supervisor is unavailable")
            if project_id in self._projects:
                raise WorkerError("worker already active for project")
            process: asyncio.subprocess.Process | None = None
            process_group_id: int | None = None
            job: WindowsJob | None = None
            start_gate: WindowsStartGate | None = None
            reader_task: asyncio.Task[None] | None = None
            stderr_task: asyncio.Task[None] | None = None
            try:
                worker_id = new_id("worker")
                target_arguments = (
                    "--project-id",
                    project_id,
                    "--worker-id",
                    worker_id,
                )
                process_arguments: tuple[str, ...]
                if os.name == "nt":
                    job = WindowsJob.create()
                    start_gate = WindowsStartGate.create()
                    process_arguments = (
                        sys.executable,
                        "-m",
                        "agent_platform.workers.bootstrap",
                        "--start-gate",
                        start_gate.name,
                        "--target-module",
                        worker_module,
                        "--",
                        *target_arguments,
                    )
                else:
                    process_arguments = (
                        sys.executable,
                        "-m",
                        worker_module,
                        *target_arguments,
                    )
                if os.name == "nt":
                    from .windows_spawn import create_windows_job_subprocess_exec

                    if job is None:
                        raise OSError("Windows worker Job Object is unavailable")
                    process = await create_windows_job_subprocess_exec(job, *process_arguments)
                else:
                    process = await asyncio.create_subprocess_exec(
                        *process_arguments,
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        start_new_session=True,
                    )
                    process_group_id = process.pid
                if job is not None and start_gate is not None:
                    await self._wait_for_start_gate(start_gate, process)
                    start_gate.release()
                    start_gate.close()
                    start_gate = None
                handle = WorkerHandle(
                    worker_id=worker_id,
                    project_id=project_id,
                    process=process,
                    decoder=FrameDecoder(),
                    outbound_sequence=0,
                    last_heartbeat_at=self._clock(),
                    pending={},
                    process_group_id=process_group_id,
                    job=job,
                )
                reader_task = asyncio.create_task(self._read_stdout(handle))
                handle.reader_task = reader_task
                stderr_task = asyncio.create_task(self._drain_stderr(handle))
                handle._stderr_task = stderr_task
                self._workers[handle.worker_id] = handle
                self._projects[project_id] = handle
                return handle
            except BaseException as start_error:
                cleanup_error: BaseException | None = None
                if process is not None or job is not None or start_gate is not None:
                    try:
                        await await_cancellation_resistant(
                            self._cleanup_partial_start(
                                process,
                                reader_task,
                                stderr_task,
                                job,
                                start_gate,
                                process_group_id,
                            )
                        )
                    except BaseException as current_cleanup_error:
                        cleanup_error = current_cleanup_error
                control_flow_errors = (asyncio.CancelledError, KeyboardInterrupt, SystemExit)
                if isinstance(start_error, control_flow_errors):
                    if cleanup_error is not None:
                        _add_secondary_cleanup_note(start_error)
                    raise start_error
                if isinstance(cleanup_error, control_flow_errors):
                    raise cleanup_error from None
                public_error = WorkerUnavailableError("worker could not be started")
                if cleanup_error is not None:
                    _add_secondary_cleanup_note(public_error)
                raise public_error from None

    async def ping(self, worker_id: str) -> IpcMessage:
        handle = self._require(worker_id)
        return await self._request(
            handle,
            "command",
            {"name": "ping"},
            timeout_seconds=self._response_timeout_seconds,
        )

    async def send(
        self,
        worker_id: str,
        message_type: MessageType,
        payload: dict[str, object],
        timeout_seconds: float = 5.0,
    ) -> IpcMessage:
        return await self._request(
            self._require(worker_id),
            message_type,
            payload,
            timeout_seconds=timeout_seconds,
        )

    async def stop(self, worker_id: str) -> None:
        handle = self._find_handle(worker_id)
        if handle is None:
            return
        stop_task = await self._ensure_stop_task(handle, graceful=True)
        await await_cancellation_resistant(stop_task)

    async def _ensure_stop_task(
        self,
        handle: WorkerHandle,
        *,
        graceful: bool,
        remove_worker_early: bool = False,
    ) -> asyncio.Task[None]:
        async with handle._state_lock:
            if handle._stop_task is None:
                handle._stopping = True
                handle._stopping_event.set()
                setup_errors: list[BaseException] = []
                loop = asyncio.get_running_loop()
                stop_coroutine = self._run_stop_task(
                    handle,
                    graceful=graceful,
                    setup_errors=setup_errors,
                )
                try:
                    handle._stop_task = loop.create_task(stop_coroutine)
                except BaseException as error:
                    stop_coroutine.close()
                    setup_errors.append(error)
                    handle._stop_task = asyncio.Task(
                        self._run_stop_task(
                            handle,
                            graceful=graceful,
                            setup_errors=setup_errors,
                        ),
                        loop=loop,
                    )
                try:
                    self._fail_pending(
                        handle,
                        WorkerUnavailableError("worker is unavailable"),
                    )
                except BaseException as error:
                    setup_errors.append(error)
            stop_task = handle._stop_task
        if remove_worker_early:
            await self._remove_worker_registry(handle)
        return stop_task

    async def _run_stop_task(
        self,
        handle: WorkerHandle,
        *,
        graceful: bool,
        setup_errors: list[BaseException],
    ) -> None:
        stop_error: BaseException | None = None
        try:
            await self._stop_handle(handle, graceful=graceful)
        except BaseException as error:
            stop_error = error
        primary_error: BaseException | None = None
        for setup_error in setup_errors:
            if primary_error is None:
                primary_error = setup_error
            elif setup_error is not primary_error:
                _add_secondary_cleanup_note(primary_error)
        if stop_error is not None:
            if primary_error is None:
                primary_error = stop_error
            elif stop_error is not primary_error:
                _add_secondary_cleanup_note(primary_error)
        if primary_error is not None:
            raise primary_error

    async def _stop_handle(self, handle: WorkerHandle, *, graceful: bool) -> None:
        first_error: BaseException | None = None

        def remember_error(error: BaseException) -> None:
            nonlocal first_error
            if first_error is None:
                first_error = error
            elif error is not first_error:
                _add_secondary_cleanup_note(first_error)

        descendants: list[Any] = []
        capture_failed = False
        try:
            descendants = await asyncio.to_thread(
                _capture_descendants_sync,
                handle.process.pid,
            )
        except BaseException as error:
            capture_failed = True
            remember_error(error)

        if capture_failed and handle.process.returncode is None:
            try:
                await self._terminate_process_tree(handle.process)
            except BaseException as error:
                remember_error(error)

        if graceful and handle.process.returncode is None:
            deadline = asyncio.get_running_loop().time() + self._shutdown_timeout_seconds
            try:
                await self._request(
                    handle,
                    "shutdown",
                    {},
                    timeout_seconds=max(0.0, deadline - asyncio.get_running_loop().time()),
                    allow_stopping=True,
                )
            except (OSError, WorkerError):
                pass
            except BaseException as error:
                remember_error(error)
            try:
                await self._close_stdin(
                    handle,
                    timeout_seconds=max(
                        0.0,
                        deadline - asyncio.get_running_loop().time(),
                    ),
                )
            except BaseException as error:
                remember_error(error)
            if handle.process.returncode is None:
                try:
                    await asyncio.wait_for(
                        handle.process.wait(),
                        timeout=max(0.0, deadline - asyncio.get_running_loop().time()),
                    )
                except TimeoutError:
                    pass
                except BaseException as error:
                    remember_error(error)

        if handle.process_group_id is not None:
            try:
                await self._terminate_posix_process_group(
                    handle.process_group_id,
                    handle.process.pid,
                )
            except BaseException as error:
                remember_error(error)
            if handle.process.returncode is None:
                try:
                    await self._terminate_process_tree(handle.process)
                except BaseException as error:
                    remember_error(error)
        elif handle.process.returncode is None:
            try:
                await self._terminate_process_tree(handle.process)
            except BaseException as error:
                remember_error(error)

        try:
            await asyncio.to_thread(_terminate_psutil_processes, descendants)
        except BaseException as error:
            remember_error(error)
        try:
            await self._close_job(handle)
        except BaseException as error:
            remember_error(error)

        if handle.process.returncode is None:
            try:
                await self._kill_process_directly(handle.process)
            except BaseException as error:
                remember_error(error)

        try:
            await self._close_stdin(
                handle,
                timeout_seconds=_PIPE_CLOSE_TIMEOUT_SECONDS,
            )
        except BaseException as error:
            remember_error(error)

        current_task = asyncio.current_task()
        cleanup_tasks = tuple(
            task for task in (handle.reader_task, handle._stderr_task) if task is not current_task
        )
        for task in cleanup_tasks:
            try:
                task.cancel()
            except BaseException as error:
                remember_error(error)
        try:
            task_results = await asyncio.gather(
                *cleanup_tasks,
                return_exceptions=True,
            )
        except BaseException as error:
            remember_error(error)
        else:
            for result in task_results:
                if isinstance(result, BaseException) and not isinstance(
                    result,
                    asyncio.CancelledError,
                ):
                    remember_error(result)
        try:
            self._fail_pending(handle, WorkerUnavailableError("worker is unavailable"))
        except BaseException as error:
            remember_error(error)
        try:
            await self._remove_registry(handle)
        except BaseException as error:
            remember_error(error)
            try:
                async with self._registry_lock:
                    if self._workers.get(handle.worker_id) is handle:
                        del self._workers[handle.worker_id]
                    if self._projects.get(handle.project_id) is handle:
                        del self._projects[handle.project_id]
            except BaseException as fallback_error:
                remember_error(fallback_error)

        if first_error is not None:
            raise first_error

    async def stop_all(self) -> None:
        await await_cancellation_resistant(self._stop_all())

    async def _stop_all(self) -> None:
        async with self._registry_lock:
            self._closing = True
            handles = list(self._projects.values())
        if not handles:
            return
        stop_tasks: list[asyncio.Task[None]] = []
        first_error: BaseException | None = None

        def remember_error(error: BaseException) -> None:
            nonlocal first_error
            if first_error is None:
                first_error = error
            elif error is not first_error:
                _add_secondary_cleanup_note(first_error)

        for handle in handles:
            try:
                stop_tasks.append(await self._ensure_stop_task(handle, graceful=True))
            except BaseException as error:
                remember_error(error)
                if handle._stop_task is not None:
                    stop_tasks.append(handle._stop_task)
        results = await asyncio.gather(*stop_tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                remember_error(result)
        if first_error is not None:
            raise first_error

    async def watch_once(self) -> None:
        now = self._clock()
        expired_handles = [
            handle
            for handle in list(self._workers.values())
            if not handle._stopping and now - handle.last_heartbeat_at > self._heartbeat_timeout
        ]
        if expired_handles:
            stop_tasks = [
                await self._ensure_stop_task(
                    handle,
                    graceful=False,
                    remove_worker_early=True,
                )
                for handle in expired_handles
            ]
            await await_cancellation_resistant(asyncio.gather(*stop_tasks))

    def get(self, worker_id: str) -> WorkerHandle | None:
        return self._workers.get(worker_id)

    def _require(self, worker_id: str) -> WorkerHandle:
        handle = self._workers.get(worker_id)
        if handle is None or handle._stopping or handle.process.returncode is not None:
            raise WorkerUnavailableError("worker is unavailable")
        return handle

    def _find_handle(self, worker_id: str) -> WorkerHandle | None:
        handle = self._workers.get(worker_id)
        if handle is not None:
            return handle
        return next(
            (
                candidate
                for candidate in self._projects.values()
                if candidate.worker_id == worker_id
            ),
            None,
        )

    async def _request(
        self,
        handle: WorkerHandle,
        message_type: MessageType,
        payload: dict[str, object],
        *,
        timeout_seconds: float,
        allow_stopping: bool = False,
    ) -> IpcMessage:
        if handle._stopping and not allow_stopping:
            raise WorkerUnavailableError("worker is unavailable")
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(0.0, timeout_seconds)
        response: asyncio.Future[IpcMessage] = loop.create_future()
        message_id: str | None = None
        write_failed = False

        def abandon_request() -> None:
            if message_id is not None:
                handle.pending.pop(message_id, None)
            if response.done():
                if not response.cancelled():
                    try:
                        response.exception()
                    except BaseException:
                        pass
            else:
                response.cancel()

        try:
            async with asyncio.timeout_at(deadline):
                async with handle._write_lock:
                    async with handle._state_lock:
                        if (
                            handle._stopping and not allow_stopping
                        ) or handle.process.returncode is not None:
                            raise WorkerUnavailableError("worker is unavailable")
                        handle.outbound_sequence += 1
                        message = IpcMessage(
                            message_id=new_id("msg"),
                            sequence=handle.outbound_sequence,
                            project_id=handle.project_id,
                            type=message_type,
                            payload=payload,
                        )
                        message_id = message.message_id
                        handle.pending[message_id] = response
                        handle._pending_event.set()
                    frame = encode_frame(message)
                    writer = handle.process.stdin
                    if writer is None:
                        raise WorkerUnavailableError("worker is unavailable")
                    writer.write(frame)
                    drain_task = loop.create_task(writer.drain())
                    try:
                        await asyncio.shield(drain_task)
                    finally:
                        if not drain_task.done():
                            drain_task.cancel()
                        await await_cancellation_resistant(
                            asyncio.gather(drain_task, return_exceptions=True)
                        )
                return await response
        except TimeoutError:
            abandon_request()
            raise WorkerTimeoutError("worker response timed out") from None
        except OSError:
            abandon_request()
            write_failed = True
        except asyncio.CancelledError:
            abandon_request()
            raise
        except BaseException:
            abandon_request()
            raise

        if write_failed:
            if allow_stopping:
                raise WorkerUnavailableError("worker is unavailable") from None
            stop_task = await self._ensure_stop_task(
                handle,
                graceful=False,
                remove_worker_early=True,
            )
            if stop_task is asyncio.current_task():
                raise WorkerUnavailableError("worker is unavailable") from None
            await await_cancellation_resistant(stop_task)
            raise WorkerUnavailableError("worker is unavailable") from None
        raise RuntimeError("worker request ended without a result")

    async def _read_stdout(self, handle: WorkerHandle) -> None:
        reader = handle.process.stdout
        if reader is None:
            await self._handle_reader_failure(
                handle,
                WorkerUnavailableError("worker is unavailable"),
            )
            return
        try:
            while chunk := await reader.read(65536):
                for message in handle.decoder.feed(chunk):
                    self._validate_inbound_message(handle, message)
                    if message.type == "heartbeat":
                        handle.last_heartbeat_at = self._clock()
                    if message.type in {"ack", "response"} and message.correlation_id:
                        pending = handle.pending.pop(message.correlation_id, None)
                        if pending is not None and not pending.done():
                            pending.set_result(message)
        except asyncio.CancelledError:
            raise
        except FramingError:
            await self._handle_reader_failure(
                handle,
                WorkerProtocolError("worker protocol failed"),
            )
        except Exception:
            await self._handle_reader_failure(
                handle,
                WorkerUnavailableError("worker is unavailable"),
            )
        else:
            if not handle._stopping:
                await self._handle_reader_failure(
                    handle,
                    WorkerUnavailableError("worker is unavailable"),
                )

    @staticmethod
    def _validate_inbound_message(handle: WorkerHandle, message: IpcMessage) -> None:
        expected_sequence = handle.last_inbound_sequence + 1
        if message.sequence != expected_sequence:
            raise FramingError("worker message sequence mismatch")
        if message.message_id in handle.seen_inbound_message_ids:
            raise FramingError("worker message replayed")
        if message.project_id != handle.project_id:
            raise FramingError("worker message project mismatch")
        if message.type == "heartbeat":
            WorkerSupervisor._validate_heartbeat(handle, message)

        handle.last_inbound_sequence = message.sequence
        handle.seen_inbound_message_ids.add(message.message_id)

    @staticmethod
    def _validate_heartbeat(handle: WorkerHandle, message: IpcMessage) -> None:
        payload = message.payload
        if set(payload) != {"worker_id", "active_task", "last_sequence"}:
            raise FramingError("worker heartbeat schema invalid")
        worker_id = payload["worker_id"]
        active_task = payload["active_task"]
        last_sequence = payload["last_sequence"]
        if type(worker_id) is not str or worker_id != handle.worker_id:
            raise FramingError("worker heartbeat identity mismatch")
        if active_task is not None and (type(active_task) is not str or not active_task):
            raise FramingError("worker heartbeat active task invalid")
        if type(last_sequence) is not int or last_sequence < 0 or last_sequence > message.sequence:
            raise FramingError("worker heartbeat sequence invalid")

    async def _handle_reader_failure(
        self,
        handle: WorkerHandle,
        error: WorkerUnavailableError,
    ) -> None:
        current_task = asyncio.current_task()
        if current_task is None:
            raise RuntimeError("worker reader task is unavailable")
        setup_errors: list[BaseException] = []
        async with handle._state_lock:
            if handle._stop_task is not None:
                self._fail_pending(handle, error)
                return
            handle._stopping = True
            handle._stopping_event.set()
            handle._stop_task = cast(asyncio.Task[None], current_task)
        try:
            self._fail_pending(handle, error)
        except BaseException as pending_error:
            setup_errors.append(pending_error)
        await self._run_stop_task(
            handle,
            graceful=False,
            setup_errors=setup_errors,
        )

    async def _drain_stderr(self, handle: WorkerHandle) -> None:
        reader = handle.process.stderr
        if reader is None:
            return
        try:
            while await reader.read(65536):
                pass
        except asyncio.CancelledError:
            raise
        except Exception:
            return

    async def _close_stdin(
        self,
        handle: WorkerHandle,
        *,
        timeout_seconds: float,
    ) -> None:
        writer = handle.process.stdin
        if writer is None:
            return
        writer.close()
        if handle.process.returncode is None:
            return
        try:
            await asyncio.wait_for(
                writer.wait_closed(),
                timeout=timeout_seconds,
            )
        except (BrokenPipeError, ConnectionResetError, OSError, TimeoutError):
            pass

    async def _cleanup_partial_start(
        self,
        process: asyncio.subprocess.Process | None,
        reader_task: asyncio.Task[None] | None,
        stderr_task: asyncio.Task[None] | None,
        job: WindowsJob | None,
        start_gate: WindowsStartGate | None,
        process_group_id: int | None,
    ) -> None:
        first_error: BaseException | None = None

        def remember_error(error: BaseException) -> None:
            nonlocal first_error
            if first_error is None:
                first_error = error
            elif error is not first_error:
                _add_secondary_cleanup_note(first_error)

        tasks = [task for task in (reader_task, stderr_task) if task is not None]
        for task in tasks:
            try:
                task.cancel()
            except BaseException as error:
                remember_error(error)
        if process is not None:
            if process_group_id is not None:
                try:
                    await self._terminate_posix_process_group(
                        process_group_id,
                        process.pid,
                    )
                except BaseException as error:
                    remember_error(error)
                    try:
                        await self._terminate_process_tree(process)
                    except BaseException as fallback_error:
                        remember_error(fallback_error)
            else:
                try:
                    await self._terminate_process_tree(process)
                except BaseException as error:
                    remember_error(error)
            if process.returncode is None:
                try:
                    await self._kill_process_directly(process)
                except BaseException as error:
                    remember_error(error)
        for resource in (job, start_gate):
            if resource is None:
                continue
            try:
                resource.close()
            except BaseException as error:
                remember_error(error)
        if process is not None:
            writer = process.stdin
            if writer is not None:
                try:
                    writer.close()
                    await asyncio.wait_for(
                        writer.wait_closed(),
                        timeout=_PIPE_CLOSE_TIMEOUT_SECONDS,
                    )
                except (OSError, TimeoutError):
                    pass
                except BaseException as error:
                    remember_error(error)
        if tasks:
            try:
                task_results = await asyncio.gather(*tasks, return_exceptions=True)
            except BaseException as error:
                remember_error(error)
            else:
                for result in task_results:
                    if isinstance(result, BaseException) and not isinstance(
                        result,
                        asyncio.CancelledError,
                    ):
                        remember_error(result)
        if first_error is not None:
            raise first_error

    @staticmethod
    async def _wait_for_start_gate(
        start_gate: WindowsStartGate,
        process: asyncio.subprocess.Process,
    ) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + _WINDOWS_START_GATE_TIMEOUT_SECONDS
        while True:
            try:
                start_gate.wait_until_opened(0.0)
                return
            except TimeoutError:
                if process.returncode is not None or loop.time() >= deadline:
                    raise OSError("worker bootstrap did not open start gate") from None
                await asyncio.sleep(0.01)

    @staticmethod
    def _fail_pending(handle: WorkerHandle, error: WorkerError) -> None:
        first_error: BaseException | None = None

        def remember_error(notification_error: BaseException) -> None:
            nonlocal first_error
            if first_error is None:
                first_error = notification_error
            elif notification_error is not first_error:
                _add_secondary_cleanup_note(first_error)

        for message_id, future in list(handle.pending.items()):
            try:
                if not future.done():
                    future.set_exception(type(error)(str(error)))
            except BaseException as notification_error:
                remember_error(notification_error)
                try:
                    asyncio.Future.cancel(future)
                except BaseException as fallback_error:
                    remember_error(fallback_error)
            finally:
                if handle.pending.get(message_id) is future:
                    del handle.pending[message_id]
        if first_error is not None:
            raise first_error

    async def _remove_registry(self, handle: WorkerHandle) -> None:
        await self._remove_registry_entries(handle)

    async def _remove_registry_entries(self, handle: WorkerHandle) -> None:
        async with self._registry_lock:
            if self._workers.get(handle.worker_id) is handle:
                del self._workers[handle.worker_id]
            if self._projects.get(handle.project_id) is handle:
                del self._projects[handle.project_id]

    @staticmethod
    async def _terminate_posix_process_group(
        process_group_id: int,
        process_id: int,
    ) -> None:
        if os.name == "nt":
            return
        killpg = getattr(os, "killpg", None)
        getpgrp = getattr(os, "getpgrp", None)
        sigterm = getattr(signal, "SIGTERM", None)
        sigkill = getattr(signal, "SIGKILL", None)
        if not callable(killpg) or not callable(getpgrp) or sigterm is None or sigkill is None:
            raise OSError("POSIX process group controls are unavailable")
        kill_group = cast(Callable[[int, int], None], killpg)
        current_group = cast(Callable[[], int], getpgrp)()
        if (
            process_group_id <= 1
            or process_id <= 1
            or process_group_id != process_id
            or process_group_id == current_group
        ):
            raise OSError("unsafe worker process group")

        async def wait_for_group_exit(timeout_seconds: float) -> bool:
            loop = asyncio.get_running_loop()
            deadline = loop.time() + timeout_seconds
            while True:
                try:
                    kill_group(process_group_id, 0)
                except ProcessLookupError:
                    return True
                except PermissionError:
                    pass
                remaining = deadline - loop.time()
                if remaining <= 0:
                    return False
                await asyncio.sleep(min(0.01, remaining))

        try:
            kill_group(process_group_id, int(sigterm))
        except ProcessLookupError:
            return
        if await wait_for_group_exit(_POSIX_GROUP_TERM_TIMEOUT_SECONDS):
            return
        try:
            kill_group(process_group_id, int(sigkill))
        except ProcessLookupError:
            return
        if not await wait_for_group_exit(_POSIX_GROUP_KILL_TIMEOUT_SECONDS):
            raise TimeoutError("worker process group did not terminate")

    @staticmethod
    async def _terminate_process_tree(process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        first_error: BaseException | None = None

        def remember_error(error: BaseException) -> None:
            nonlocal first_error
            if first_error is None:
                first_error = error
            elif error is not first_error:
                _add_secondary_cleanup_note(first_error)

        try:
            await asyncio.to_thread(_terminate_process_tree_sync, process.pid)
        except BaseException as error:
            remember_error(error)
        if process.returncode is None and first_error is None:
            try:
                await asyncio.wait_for(process.wait(), timeout=1.0)
            except TimeoutError:
                pass
            except BaseException as error:
                remember_error(error)
        if process.returncode is None:
            try:
                await WorkerSupervisor._kill_process_directly(process)
            except BaseException as error:
                remember_error(error)
        if first_error is not None:
            raise first_error

    @staticmethod
    async def _kill_process_directly(process: asyncio.subprocess.Process) -> None:
        first_error: BaseException | None = None

        def remember_error(error: BaseException) -> None:
            nonlocal first_error
            if first_error is None:
                first_error = error
            elif error is not first_error:
                _add_secondary_cleanup_note(first_error)

        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            except BaseException as error:
                remember_error(error)
        try:
            await asyncio.wait_for(process.wait(), timeout=1.0)
        except BaseException as error:
            remember_error(error)
        if first_error is not None:
            raise first_error

    async def _remove_worker_registry(self, handle: WorkerHandle) -> None:
        async with self._registry_lock:
            if self._workers.get(handle.worker_id) is handle:
                del self._workers[handle.worker_id]

    @staticmethod
    async def _close_job(handle: WorkerHandle) -> None:
        job = handle.job
        if job is None:
            return
        try:
            job.close()
        except BaseException as error:
            try:
                WindowsJob.close(job)
            except BaseException:
                _add_secondary_cleanup_note(error)
            raise error
