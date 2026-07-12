import asyncio
import os
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


class WorkerError(RuntimeError):
    """Base class for sanitized worker lifecycle errors."""


class WorkerUnavailableError(WorkerError):
    """Raised when a worker can no longer accept or answer messages."""


class WorkerProtocolError(WorkerUnavailableError):
    """Raised when a worker writes invalid IPC output."""


class WorkerTimeoutError(WorkerError):
    """Raised when a worker does not answer within the response deadline."""


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

    async def start(
        self,
        project_id: str,
        worker_module: str = "agent_platform.workers.main",
    ) -> WorkerHandle:
        if not project_id or not project_id.isascii() or not project_id.isprintable():
            raise ValueError("invalid project id")
        async with self._registry_lock:
            if project_id in self._projects:
                raise WorkerError("worker already active for project")
            process: asyncio.subprocess.Process | None = None
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
                    )
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
                    job=job,
                )
                reader_task = asyncio.create_task(self._read_stdout(handle))
                handle.reader_task = reader_task
                stderr_task = asyncio.create_task(self._drain_stderr(handle))
                handle._stderr_task = stderr_task
                self._workers[handle.worker_id] = handle
                self._projects[project_id] = handle
                return handle
            except BaseException as error:
                if process is not None or job is not None or start_gate is not None:
                    await await_cancellation_resistant(
                        self._cleanup_partial_start(
                            process,
                            reader_task,
                            stderr_task,
                            job,
                            start_gate,
                        )
                    )
                if isinstance(error, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                    raise
                raise WorkerUnavailableError("worker could not be started") from None

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
                self._fail_pending(handle, WorkerUnavailableError("worker is unavailable"))
                handle._stop_task = asyncio.create_task(
                    self._stop_handle(handle, graceful=graceful)
                )
            stop_task = handle._stop_task
        if remove_worker_early:
            await self._remove_worker_registry(handle)
        return stop_task

    async def _stop_handle(self, handle: WorkerHandle, *, graceful: bool) -> None:
        descendants = await asyncio.to_thread(_capture_descendants_sync, handle.process.pid)
        try:
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
                await self._close_stdin(handle)
                try:
                    await asyncio.wait_for(
                        handle.process.wait(),
                        timeout=max(0.0, deadline - asyncio.get_running_loop().time()),
                    )
                except TimeoutError:
                    await self._terminate_process_tree(handle.process)
            elif handle.process.returncode is None:
                await self._terminate_process_tree(handle.process)
        finally:
            await asyncio.to_thread(_terminate_psutil_processes, descendants)
            await self._close_job(handle)
            handle.reader_task.cancel()
            handle._stderr_task.cancel()
            await asyncio.gather(
                handle.reader_task,
                handle._stderr_task,
                return_exceptions=True,
            )
            self._fail_pending(handle, WorkerUnavailableError("worker is unavailable"))
            await self._remove_registry(handle)

    async def stop_all(self) -> None:
        handles = list(self._projects.values())
        if not handles:
            return
        stop_tasks = [await self._ensure_stop_task(handle, graceful=True) for handle in handles]
        results = await await_cancellation_resistant(
            asyncio.gather(*stop_tasks, return_exceptions=True)
        )
        for result in results:
            if isinstance(result, BaseException):
                raise result

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
        response: asyncio.Future[IpcMessage] = loop.create_future()
        write_failed = False
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
                handle.pending[message.message_id] = response
                handle._pending_event.set()
            try:
                frame = encode_frame(message)
                writer = handle.process.stdin
                if writer is None:
                    raise WorkerUnavailableError("worker is unavailable")
                writer.write(frame)
                drain_task = asyncio.create_task(writer.drain())
                await await_cancellation_resistant(drain_task)
            except OSError:
                handle.pending.pop(message.message_id, None)
                if not response.done():
                    response.cancel()
                write_failed = True
            except BaseException:
                handle.pending.pop(message.message_id, None)
                if not response.done():
                    response.cancel()
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

        try:
            return await asyncio.wait_for(response, timeout=timeout_seconds)
        except TimeoutError:
            handle.pending.pop(message.message_id, None)
            if not response.done():
                response.cancel()
            raise WorkerTimeoutError("worker response timed out") from None
        except asyncio.CancelledError:
            handle.pending.pop(message.message_id, None)
            if not response.done():
                response.cancel()
            raise

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
        async with handle._state_lock:
            if handle._stop_task is not None:
                self._fail_pending(handle, error)
                return
            handle._stopping = True
            handle._stopping_event.set()
            handle._stop_task = cast(asyncio.Task[None], current_task)
        self._fail_pending(handle, error)
        await self._remove_worker_registry(handle)
        try:
            await self._terminate_process_tree(handle.process)
        finally:
            try:
                await self._close_job(handle)
            finally:
                handle._stderr_task.cancel()
                await asyncio.gather(handle._stderr_task, return_exceptions=True)
                await self._remove_registry(handle)

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

    async def _close_stdin(self, handle: WorkerHandle) -> None:
        writer = handle.process.stdin
        if writer is None:
            return
        writer.close()
        try:
            await writer.wait_closed()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    async def _cleanup_partial_start(
        self,
        process: asyncio.subprocess.Process | None,
        reader_task: asyncio.Task[None] | None,
        stderr_task: asyncio.Task[None] | None,
        job: WindowsJob | None,
        start_gate: WindowsStartGate | None,
    ) -> None:
        tasks = [task for task in (reader_task, stderr_task) if task is not None]
        for task in tasks:
            task.cancel()
        try:
            if process is not None:
                await self._terminate_process_tree(process)
        finally:
            for resource in (job, start_gate):
                if resource is None:
                    continue
                try:
                    resource.close()
                except OSError:
                    pass
        if process is not None:
            writer = process.stdin
            if writer is not None:
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

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
        pending = list(handle.pending.values())
        handle.pending.clear()
        for future in pending:
            if not future.done():
                future.set_exception(type(error)(str(error)))

    async def _remove_registry(self, handle: WorkerHandle) -> None:
        async with self._registry_lock:
            if self._workers.get(handle.worker_id) is handle:
                del self._workers[handle.worker_id]
            if self._projects.get(handle.project_id) is handle:
                del self._projects[handle.project_id]

    @staticmethod
    async def _terminate_process_tree(process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        await asyncio.to_thread(_terminate_process_tree_sync, process.pid)
        if process.returncode is not None:
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=1.0)
        except TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()

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
        except OSError:
            pass
