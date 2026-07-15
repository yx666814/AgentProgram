import asyncio
import contextvars
import ctypes
import hashlib
import json
import os
import signal
import sys
import tempfile
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import psutil  # type: ignore[import-untyped]
import pytest
from tests.fixtures.atomic_job_chain_worker import atomic_job_chain_paths

import agent_platform.infrastructure.workers.supervisor as supervisor_module
from agent_platform.infrastructure.logging.configure import configure_logging
from agent_platform.infrastructure.workers.supervisor import (
    WorkerError,
    WorkerHandle,
    WorkerProtocolError,
    WorkerSupervisor,
    WorkerTimeoutError,
    WorkerUnavailableError,
)
from agent_platform.infrastructure.workers.windows_job import WindowsJob, WindowsStartGate
from agent_platform.interfaces.ipc.messages import IpcMessage

if os.name == "nt":
    import agent_platform.infrastructure.workers.windows_spawn as windows_spawn_module


@dataclass(frozen=True)
class _ProcessIdentity:
    role: str
    pid: int
    create_time: float


class _FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, duration: timedelta) -> None:
        self.now += duration


class _SteppingClock:
    def __init__(self) -> None:
        self._now = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        self._now += timedelta(seconds=1)
        return self._now


def test_secondary_cleanup_note_failure_does_not_replace_primary() -> None:
    primary_error = RuntimeError("primary failure")
    original_cause = OSError("original cause")
    original_context = ValueError("original context")
    primary_error.__cause__ = original_cause
    primary_error.__context__ = original_context
    primary_error.__suppress_context__ = True
    primary_error.__dict__["__notes__"] = "invalid notes"

    supervisor_module._add_secondary_cleanup_note(primary_error)

    assert primary_error.__cause__ is original_cause
    assert primary_error.__context__ is original_context
    assert primary_error.__suppress_context__ is True
    assert primary_error.__dict__["__notes__"] == "invalid notes"


async def _terminate_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=1.0)
    except TimeoutError:
        process.kill()
        await process.wait()


def _child_pid_path(project_id: str) -> Path:
    return Path(tempfile.gettempdir()) / f"agent-platform-{project_id}.child.pid"


def _import_marker_path(project_id: str) -> Path:
    return Path(tempfile.gettempdir()) / f"agent-platform-{project_id}.import.marker"


async def _wait_for_child_pid(path: Path) -> int:
    for _ in range(200):
        raw_pid = await asyncio.to_thread(_read_text_if_present, path)
        if raw_pid:
            return int(raw_pid)
        await asyncio.sleep(0.01)
    raise AssertionError("child PID fixture was not published")


async def _wait_for_pid_pair(path: Path) -> tuple[int, int]:
    for _ in range(200):
        raw_pid_pair = await asyncio.to_thread(_read_text_if_present, path)
        if raw_pid_pair:
            first_pid, second_pid = raw_pid_pair.split("|", maxsplit=1)
            return int(first_pid), int(second_pid)
        await asyncio.sleep(0.01)
    raise AssertionError("process chain fixture was not published")


async def _wait_for_pid_exit(pid: int) -> None:
    for _ in range(200):
        if not psutil.pid_exists(pid):
            return
        await asyncio.sleep(0.01)
    raise AssertionError("child process survived worker cleanup")


def _read_text_if_present(path: Path) -> str | None:
    try:
        return path.read_text(encoding="ascii")
    except FileNotFoundError:
        return None


def _kill_pid_if_alive(pid: int) -> None:
    try:
        process = psutil.Process(pid)
        process.kill()
        process.wait(timeout=1)
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.TimeoutExpired):
        pass


def _capture_process_identity(role: str, pid: int) -> _ProcessIdentity:
    process = psutil.Process(pid)
    return _ProcessIdentity(role=role, pid=pid, create_time=process.create_time())


def _identity_is_alive(identity: _ProcessIdentity) -> bool:
    try:
        process = psutil.Process(identity.pid)
        return bool(process.create_time() == identity.create_time and process.is_running())
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
        return False


def _surviving_identities(
    identities: tuple[_ProcessIdentity, ...],
) -> tuple[_ProcessIdentity, ...]:
    return tuple(identity for identity in identities if _identity_is_alive(identity))


async def _wait_for_identity_exit(
    identities: tuple[_ProcessIdentity, ...],
) -> tuple[_ProcessIdentity, ...]:
    for _ in range(200):
        survivors = await asyncio.to_thread(_surviving_identities, identities)
        if not survivors:
            return ()
        await asyncio.sleep(0.01)
    return await asyncio.to_thread(_surviving_identities, identities)


def _kill_process_identities(identities: tuple[_ProcessIdentity, ...]) -> None:
    for identity in reversed(identities):
        try:
            process = psutil.Process(identity.pid)
            if process.create_time() != identity.create_time:
                continue
            process.kill()
            process.wait(timeout=1)
        except (
            psutil.AccessDenied,
            psutil.NoSuchProcess,
            psutil.TimeoutExpired,
            psutil.ZombieProcess,
        ):
            pass


async def test_supervisor_starts_pings_and_stops_real_worker() -> None:
    supervisor = WorkerSupervisor(heartbeat_timeout=timedelta(seconds=10))
    handle = await supervisor.start("project_1")

    try:
        response = await supervisor.ping(handle.worker_id)

        assert response.type == "ack"
        assert response.payload == {"status": "ok"}
        assert response.correlation_id is not None
        assert handle.process.returncode is None
        assert supervisor.get(handle.worker_id) is handle

        await supervisor.stop(handle.worker_id)

        assert handle.process.returncode == 0
        assert supervisor.get(handle.worker_id) is None
    finally:
        await supervisor.stop_all()


@pytest.mark.skipif(os.name != "nt", reason="Windows atomic spawn only")
async def test_supervisor_passes_canonical_worker_id_to_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spawn_arguments: list[tuple[object, ...]] = []
    spawn_keyword_arguments: list[dict[str, object]] = []
    real_spawn = windows_spawn_module.create_windows_job_subprocess_exec

    async def recording_spawn(
        job: WindowsJob,
        *args: str,
        **kwargs: object,
    ) -> asyncio.subprocess.Process:
        spawn_arguments.append(args)
        spawn_keyword_arguments.append(kwargs)
        assert kwargs == {}
        return await real_spawn(job, *args)

    monkeypatch.setattr(
        windows_spawn_module,
        "create_windows_job_subprocess_exec",
        recording_spawn,
    )
    supervisor = WorkerSupervisor(heartbeat_timeout=timedelta(seconds=10))
    handle = await supervisor.start("project_canonical_identity")

    try:
        assert spawn_arguments[0][:3] == (
            sys.executable,
            "-m",
            "agent_platform.workers.bootstrap",
        )
        target_index = spawn_arguments[0].index("--target-module") + 1
        assert spawn_arguments[0][target_index] == "agent_platform.workers.main"
        worker_id_index = spawn_arguments[0].index("--worker-id") + 1
        assert spawn_arguments[0][worker_id_index] == handle.worker_id
        assert spawn_keyword_arguments == [{}]
        assert handle.process_group_id is None
        assert (await supervisor.ping(handle.worker_id)).payload == {"status": "ok"}
    finally:
        await supervisor.stop_all()


@pytest.mark.skipif(os.name == "nt", reason="POSIX process group spawn only")
async def test_posix_spawn_starts_a_new_process_group() -> None:
    supervisor = WorkerSupervisor(heartbeat_timeout=timedelta(seconds=10))
    handle = await supervisor.start(
        "project_posix_process_group",
        "tests.fixtures.silent_worker",
    )

    try:
        assert handle.process_group_id == handle.process.pid
        getpgrp = cast(Callable[[], int], os.getpgrp)  # type: ignore[attr-defined]
        assert handle.process_group_id != getpgrp()
    finally:
        await supervisor.stop_all()


@pytest.mark.skipif(os.name == "nt", reason="POSIX process group cleanup only")
async def test_posix_group_cleanup_never_signals_backend_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signalled: list[tuple[int, int]] = []

    def unexpected_killpg(process_group_id: int, signal_number: int) -> None:
        signalled.append((process_group_id, signal_number))

    monkeypatch.setattr(os, "killpg", unexpected_killpg)
    current_group = cast(Callable[[], int], os.getpgrp)()  # type: ignore[attr-defined]

    with pytest.raises(OSError, match="unsafe worker process group"):
        await WorkerSupervisor._terminate_posix_process_group(
            current_group,
            current_group,
        )

    assert signalled == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX process group cleanup only")
async def test_posix_group_cleanup_escalates_from_term_to_kill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process_group_id = 12345
    signalled: list[int] = []
    killed = False
    sigkill = cast(int, signal.SIGKILL)  # type: ignore[attr-defined]

    def controlled_killpg(actual_group_id: int, signal_number: int) -> None:
        nonlocal killed
        assert actual_group_id == process_group_id
        signalled.append(signal_number)
        if signal_number == sigkill:
            killed = True
        elif signal_number == 0 and killed:
            raise ProcessLookupError

    monkeypatch.setattr(os, "killpg", controlled_killpg)
    monkeypatch.setattr(os, "getpgrp", lambda: process_group_id + 1)
    monkeypatch.setattr(supervisor_module, "_POSIX_GROUP_TERM_TIMEOUT_SECONDS", 0.0)

    await WorkerSupervisor._terminate_posix_process_group(
        process_group_id,
        process_group_id,
    )

    assert signalled == [signal.SIGTERM, 0, sigkill, 0]


async def test_watch_once_terminates_worker_after_heartbeat_timeout() -> None:
    clock = _FakeClock()
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=1),
        shutdown_timeout_seconds=0.1,
        clock=clock,
    )
    handle = await supervisor.start("project_silent", "tests.fixtures.silent_worker")

    try:
        clock.advance(timedelta(seconds=1, microseconds=1))

        await supervisor.watch_once()

        assert supervisor.get(handle.worker_id) is None
        assert handle.process.returncode is not None
    finally:
        await supervisor.stop_all()


async def test_start_rejects_duplicate_project_without_replacing_worker() -> None:
    supervisor = WorkerSupervisor(heartbeat_timeout=timedelta(seconds=10))
    original = await supervisor.start("project_duplicate")

    try:
        with pytest.raises(WorkerError, match="already active"):
            await supervisor.start("project_duplicate")

        assert supervisor.get(original.worker_id) is original
        assert (await supervisor.ping(original.worker_id)).payload == {"status": "ok"}
    finally:
        await supervisor.stop_all()


@pytest.mark.parametrize(
    "project_id",
    ["", "project\r\nSECRET_PROJECT", "project\tbad", "项目"],
)
async def test_start_rejects_unsafe_project_id(project_id: str) -> None:
    supervisor = WorkerSupervisor(heartbeat_timeout=timedelta(seconds=10))

    try:
        with pytest.raises(ValueError, match="invalid project id"):
            await supervisor.start(project_id)
    finally:
        await supervisor.stop_all()


async def test_send_timeout_removes_pending_and_ignores_late_response() -> None:
    supervisor = WorkerSupervisor(heartbeat_timeout=timedelta(seconds=10))
    handle = await supervisor.start("project_delayed", "tests.fixtures.delayed_worker")

    try:
        with pytest.raises(WorkerTimeoutError, match="response timed out"):
            await supervisor.send(
                handle.worker_id,
                "command",
                {"name": "slow"},
                timeout_seconds=0.05,
            )
        assert handle.pending == {}

        await asyncio.sleep(0.25)

        assert handle.pending == {}
        response = await supervisor.send(
            handle.worker_id,
            "command",
            {"name": "second"},
            timeout_seconds=1.0,
        )
        assert response.payload == {"status": "late"}
        assert handle.pending == {}
    finally:
        await supervisor.stop_all()


async def test_shutdown_deadline_covers_write_lock_acquisition() -> None:
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        shutdown_timeout_seconds=0.1,
    )
    handle: WorkerHandle | None = None
    stop_task: asyncio.Task[None] | None = None

    try:
        handle = await supervisor.start(
            "project_shutdown_write_lock_deadline",
            "tests.fixtures.silent_worker",
        )
        await handle._write_lock.acquire()
        stop_task = asyncio.create_task(supervisor.stop(handle.worker_id))

        done, _ = await asyncio.wait({stop_task}, timeout=1.5)

        assert stop_task in done
        await stop_task
        assert handle.process.returncode is not None
        assert supervisor.get(handle.worker_id) is None
    finally:
        if handle is not None and handle._write_lock.locked():
            handle._write_lock.release()
        if stop_task is not None:
            await asyncio.gather(stop_task, return_exceptions=True)
        await asyncio.gather(supervisor.stop_all(), return_exceptions=True)
        if handle is not None:
            await _terminate_process(handle.process)


async def test_shutdown_deadline_cancels_and_joins_backpressured_drain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        shutdown_timeout_seconds=0.1,
    )
    handle: WorkerHandle | None = None
    stop_task: asyncio.Task[None] | None = None
    allow_drain = asyncio.Event()
    drain_started = asyncio.Event()
    drain_cancelled = asyncio.Event()
    drain_converged = asyncio.Event()

    try:
        handle = await supervisor.start(
            "project_shutdown_drain_deadline",
            "tests.fixtures.silent_worker",
        )
        writer = handle.process.stdin
        assert writer is not None

        async def backpressured_drain() -> None:
            drain_started.set()
            try:
                await allow_drain.wait()
            except asyncio.CancelledError:
                drain_cancelled.set()
                raise
            finally:
                drain_converged.set()

        monkeypatch.setattr(writer, "drain", backpressured_drain)
        stop_task = asyncio.create_task(supervisor.stop(handle.worker_id))
        await asyncio.wait_for(drain_started.wait(), timeout=1.0)

        done, _ = await asyncio.wait({stop_task}, timeout=1.5)

        assert stop_task in done
        await stop_task
        assert drain_cancelled.is_set()
        assert drain_converged.is_set()
        assert handle._write_lock.locked() is False
        assert handle.process.returncode is not None
        assert supervisor.get(handle.worker_id) is None
    finally:
        allow_drain.set()
        if stop_task is not None:
            await asyncio.gather(stop_task, return_exceptions=True)
        await asyncio.gather(supervisor.stop_all(), return_exceptions=True)
        if handle is not None:
            await _terminate_process(handle.process)


async def test_stdin_close_waits_only_after_worker_termination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        shutdown_timeout_seconds=0.1,
    )
    handle: WorkerHandle | None = None
    waited_while_alive = asyncio.Event()
    wait_cancelled = asyncio.Event()
    waited_after_exit = asyncio.Event()

    try:
        handle = await supervisor.start(
            "project_stdin_close_order",
            "tests.fixtures.silent_worker",
        )
        writer = handle.process.stdin
        assert writer is not None

        async def controlled_wait_closed() -> None:
            if handle is not None and handle.process.returncode is None:
                waited_while_alive.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    wait_cancelled.set()
                    raise
            waited_after_exit.set()

        monkeypatch.setattr(writer, "wait_closed", controlled_wait_closed)

        await supervisor.stop(handle.worker_id)

        assert waited_while_alive.is_set() is False
        assert wait_cancelled.is_set() is False
        assert waited_after_exit.is_set()
        assert handle.process.returncode is not None
    finally:
        await asyncio.gather(supervisor.stop_all(), return_exceptions=True)
        if handle is not None:
            await _terminate_process(handle.process)


async def test_external_cancellation_converges_drain_and_remains_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supervisor = WorkerSupervisor(heartbeat_timeout=timedelta(seconds=10))
    handle: WorkerHandle | None = None
    send_task: asyncio.Task[IpcMessage] | None = None
    allow_drain = asyncio.Event()
    drain_started = asyncio.Event()
    drain_cancelled = asyncio.Event()
    drain_converged = asyncio.Event()

    try:
        handle = await supervisor.start(
            "project_cancelled_drain",
            "tests.fixtures.silent_worker",
        )
        writer = handle.process.stdin
        assert writer is not None

        async def backpressured_drain() -> None:
            drain_started.set()
            try:
                await allow_drain.wait()
            except asyncio.CancelledError:
                drain_cancelled.set()
                raise
            finally:
                drain_converged.set()

        monkeypatch.setattr(writer, "drain", backpressured_drain)
        send_task = asyncio.create_task(
            supervisor.send(
                handle.worker_id,
                "command",
                {"name": "cancelled_drain"},
                timeout_seconds=5.0,
            )
        )
        await asyncio.wait_for(drain_started.wait(), timeout=1.0)
        send_task.cancel()

        done, _ = await asyncio.wait({send_task}, timeout=0.5)

        assert send_task in done
        with pytest.raises(asyncio.CancelledError):
            await send_task
        assert drain_cancelled.is_set()
        assert drain_converged.is_set()
        assert handle._write_lock.locked() is False
        assert handle.pending == {}
    finally:
        allow_drain.set()
        if send_task is not None:
            await asyncio.gather(send_task, return_exceptions=True)
        await asyncio.gather(supervisor.stop_all(), return_exceptions=True)
        if handle is not None:
            await _terminate_process(handle.process)


async def test_real_pipe_backpressure_does_not_block_shutdown_cleanup() -> None:
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        shutdown_timeout_seconds=0.1,
    )
    handle: WorkerHandle | None = None
    send_task: asyncio.Task[IpcMessage] | None = None
    stop_task: asyncio.Task[None] | None = None
    response_future: asyncio.Future[IpcMessage] | None = None
    loop = asyncio.get_running_loop()
    original_exception_handler = loop.get_exception_handler()
    unexpected_contexts: list[dict[str, object]] = []

    def capture_unexpected(
        _: asyncio.AbstractEventLoop,
        context: dict[str, object],
    ) -> None:
        unexpected_contexts.append(context)

    loop.set_exception_handler(capture_unexpected)
    try:
        handle = await supervisor.start(
            "project_real_pipe_backpressure",
            "tests.fixtures.nonreading_worker",
        )
        send_task = asyncio.create_task(
            supervisor.send(
                handle.worker_id,
                "command",
                {"blob": "x" * 900_000},
                timeout_seconds=5.0,
            )
        )
        for _ in range(200):
            if handle._write_lock.locked():
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("real pipe backpressure did not hold the write lock")
        assert len(handle.pending) == 1
        response_future = next(iter(handle.pending.values()))

        stop_task = asyncio.create_task(supervisor.stop_all())
        done, _ = await asyncio.wait({stop_task}, timeout=1.5)

        assert stop_task in done
        await stop_task
        with pytest.raises(WorkerUnavailableError, match="worker is unavailable"):
            await send_task
        assert handle._write_lock.locked() is False
        assert handle.pending == {}
        assert handle.process.returncode is not None
        assert supervisor._workers == {}
        assert supervisor._projects == {}
        assert getattr(response_future, "_log_traceback", True) is False
        await asyncio.sleep(0)
        assert unexpected_contexts == []
    finally:
        if handle is not None and handle.process.returncode is None:
            await _terminate_process(handle.process)
        if send_task is not None:
            await asyncio.gather(send_task, return_exceptions=True)
        if stop_task is not None:
            await asyncio.gather(stop_task, return_exceptions=True)
        await asyncio.gather(supervisor.stop_all(), return_exceptions=True)
        loop.set_exception_handler(original_exception_handler)


async def test_pending_send_fails_and_registry_clears_when_worker_exits() -> None:
    supervisor = WorkerSupervisor(heartbeat_timeout=timedelta(seconds=10))
    handle = await supervisor.start("project_crash", "tests.fixtures.silent_worker")
    send_task = asyncio.create_task(
        supervisor.send(
            handle.worker_id,
            "command",
            {"name": "never_answered"},
            timeout_seconds=5.0,
        )
    )

    try:
        await asyncio.wait_for(handle._pending_event.wait(), timeout=1.0)
        handle.process.kill()

        with pytest.raises(WorkerUnavailableError, match="worker is unavailable"):
            await send_task
        await handle.reader_task

        assert handle.pending == {}
        assert supervisor.get(handle.worker_id) is None
    finally:
        await supervisor.stop_all()


async def test_protocol_corruption_fails_pending_and_terminates_worker() -> None:
    supervisor = WorkerSupervisor(heartbeat_timeout=timedelta(seconds=10))
    handle = await supervisor.start("project_corrupt", "tests.fixtures.corrupt_worker")

    try:
        with pytest.raises(WorkerProtocolError, match="protocol failed"):
            await supervisor.send(
                handle.worker_id,
                "command",
                {"name": "trigger_corruption"},
                timeout_seconds=2.0,
            )
        await handle.reader_task

        assert handle.pending == {}
        assert supervisor.get(handle.worker_id) is None
        assert handle.process.returncode is not None
    finally:
        await supervisor.stop_all()
        await _terminate_process(handle.process)


async def test_replayed_response_fails_second_pending_and_removes_worker() -> None:
    supervisor = WorkerSupervisor(heartbeat_timeout=timedelta(seconds=10))
    handle = await supervisor.start(
        "project_response_replay",
        "tests.fixtures.invalid_inbound_worker",
    )

    try:
        first = await supervisor.send(
            handle.worker_id,
            "command",
            {"name": "first"},
            timeout_seconds=1.0,
        )
        assert first.payload == {"status": "response_1"}

        with pytest.raises(WorkerProtocolError, match="protocol failed"):
            await supervisor.send(
                handle.worker_id,
                "command",
                {"name": "second"},
                timeout_seconds=1.0,
            )
        await handle.reader_task

        assert handle.pending == {}
        assert handle.process.returncode is not None
        assert supervisor.get(handle.worker_id) is None
    finally:
        await supervisor.stop_all()
        await _terminate_process(handle.process)


async def test_skipped_response_sequence_is_protocol_error() -> None:
    supervisor = WorkerSupervisor(heartbeat_timeout=timedelta(seconds=10))
    handle = await supervisor.start(
        "project_response_skipped",
        "tests.fixtures.invalid_inbound_worker",
    )

    try:
        with pytest.raises(WorkerProtocolError, match="protocol failed"):
            await supervisor.send(
                handle.worker_id,
                "command",
                {"name": "skip"},
                timeout_seconds=1.0,
            )
        await handle.reader_task

        assert handle.pending == {}
        assert handle.process.returncode is not None
        assert supervisor.get(handle.worker_id) is None
    finally:
        await supervisor.stop_all()
        await _terminate_process(handle.process)


async def test_repeated_heartbeat_cannot_refresh_liveness() -> None:
    clock = _SteppingClock()
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        clock=clock,
    )
    handle = await supervisor.start(
        "project_heartbeat_repeat",
        "tests.fixtures.invalid_inbound_worker",
    )
    started_at = handle.last_heartbeat_at

    try:
        for _ in range(200):
            if handle.last_heartbeat_at > started_at:
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("first heartbeat was not processed")
        accepted_at = handle.last_heartbeat_at

        with pytest.raises(WorkerProtocolError, match="protocol failed"):
            await supervisor.send(
                handle.worker_id,
                "command",
                {"name": "repeat_heartbeat"},
                timeout_seconds=1.0,
            )
        await handle.reader_task

        assert handle.last_heartbeat_at == accepted_at
        assert handle.process.returncode is not None
        assert supervisor.get(handle.worker_id) is None
    finally:
        await supervisor.stop_all()
        await _terminate_process(handle.process)


@pytest.mark.parametrize(
    "mode",
    [
        "heartbeat_forged",
        "heartbeat_bool",
        "heartbeat_empty_task",
        "heartbeat_future",
        "heartbeat_secret",
    ],
)
async def test_invalid_heartbeat_schema_cannot_refresh_liveness(mode: str) -> None:
    clock = _SteppingClock()
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        clock=clock,
    )
    handle = await supervisor.start(
        f"project_{mode}",
        "tests.fixtures.invalid_inbound_worker",
    )
    started_at = handle.last_heartbeat_at

    try:
        with pytest.raises(WorkerProtocolError, match="protocol failed") as raised:
            await supervisor.send(
                handle.worker_id,
                "command",
                {"name": "invalid_heartbeat"},
                timeout_seconds=1.0,
            )
        await handle.reader_task

        assert "SECRET_HEARTBEAT_PAYLOAD" not in str(raised.value)
        assert handle.last_heartbeat_at == started_at
        assert handle.process.returncode is not None
        assert supervisor.get(handle.worker_id) is None
    finally:
        await supervisor.stop_all()
        await _terminate_process(handle.process)


@pytest.mark.parametrize(
    "mode",
    ["heartbeat_top_level_extra", "response_top_level_extra"],
)
async def test_unknown_top_level_field_is_protocol_error_before_state_change(mode: str) -> None:
    clock = _SteppingClock()
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        clock=clock,
    )
    handle = await supervisor.start(
        f"project_{mode}",
        "tests.fixtures.invalid_inbound_worker",
    )
    started_at = handle.last_heartbeat_at

    try:
        with pytest.raises(WorkerProtocolError, match="protocol failed") as raised:
            await supervisor.send(
                handle.worker_id,
                "command",
                {"name": "unknown_top_level"},
                timeout_seconds=1.0,
            )
        await handle.reader_task

        assert "SECRET_UNKNOWN_TOP_LEVEL_FIELD" not in str(raised.value)
        assert handle.last_heartbeat_at == started_at
        assert handle.pending == {}
        assert handle.process.returncode is not None
        assert supervisor.get(handle.worker_id) is None
    finally:
        await supervisor.stop_all()
        await _terminate_process(handle.process)


async def test_concurrent_stop_callers_wait_for_same_cleanup() -> None:
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        shutdown_timeout_seconds=0.2,
    )
    handle = await supervisor.start("project_concurrent_stop", "tests.fixtures.silent_worker")
    first_stop = asyncio.create_task(supervisor.stop(handle.worker_id))

    try:
        await asyncio.wait_for(handle._stopping_event.wait(), timeout=1.0)

        await supervisor.stop(handle.worker_id)

        assert first_stop.done()
        assert handle.process.returncode is not None
        assert supervisor.get(handle.worker_id) is None
        await supervisor.stop(handle.worker_id)
    finally:
        await first_stop
        await supervisor.stop_all()


async def test_heartbeat_timeout_terminates_full_process_tree() -> None:
    clock = _FakeClock()
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=1),
        shutdown_timeout_seconds=0.1,
        clock=clock,
    )
    project_id = f"tree_{uuid4().hex}"
    pid_path = _child_pid_path(project_id)
    pid_path.unlink(missing_ok=True)
    handle = await supervisor.start(project_id, "tests.fixtures.child_worker")
    child_pid: int | None = None

    try:
        child_pid = await _wait_for_child_pid(pid_path)
        assert psutil.pid_exists(child_pid)
        clock.advance(timedelta(seconds=2))

        await supervisor.watch_once()

        assert supervisor.get(handle.worker_id) is None
        assert handle.process.returncode is not None
        assert not psutil.pid_exists(child_pid)
    finally:
        await supervisor.stop_all()
        await _terminate_process(handle.process)
        if child_pid is not None:
            await asyncio.to_thread(_kill_pid_if_alive, child_pid)
        pid_path.unlink(missing_ok=True)


async def test_stop_all_finishes_cleanup_before_propagating_cancellation() -> None:
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        shutdown_timeout_seconds=0.2,
    )
    handles: list[WorkerHandle] = []
    stop_all_task: asyncio.Task[None] | None = None

    try:
        handles.append(
            await supervisor.start("project_cancel_all_1", "tests.fixtures.silent_worker")
        )
        handles.append(
            await supervisor.start("project_cancel_all_2", "tests.fixtures.silent_worker")
        )
        stop_all_task = asyncio.create_task(supervisor.stop_all())
        await asyncio.wait_for(
            asyncio.gather(*(handle._stopping_event.wait() for handle in handles)),
            timeout=1.0,
        )
        stop_all_task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await stop_all_task

        assert all(handle.process.returncode is not None for handle in handles)
        assert all(supervisor.get(handle.worker_id) is None for handle in handles)
    finally:
        if stop_all_task is not None:
            await asyncio.gather(stop_all_task, return_exceptions=True)
        await asyncio.gather(supervisor.stop_all(), return_exceptions=True)
        for handle in handles:
            await _terminate_process(handle.process)


@pytest.mark.parametrize("cancel_stop_all", [False, True])
async def test_stop_all_waits_for_in_flight_start_and_stops_worker(
    monkeypatch: pytest.MonkeyPatch,
    cancel_stop_all: bool,
) -> None:
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        shutdown_timeout_seconds=0.2,
    )
    spawn_entered = asyncio.Event()
    allow_spawn = asyncio.Event()
    spawn_count = 0
    handle: WorkerHandle | None = None
    start_task: asyncio.Task[WorkerHandle] | None = None
    stop_all_task: asyncio.Task[None] | None = None
    late_start_task: asyncio.Task[WorkerHandle] | None = None

    if os.name == "nt":
        real_windows_spawn = windows_spawn_module.create_windows_job_subprocess_exec

        async def controlled_windows_spawn(
            job: WindowsJob,
            *args: str,
        ) -> asyncio.subprocess.Process:
            nonlocal spawn_count
            spawn_count += 1
            spawn_entered.set()
            await allow_spawn.wait()
            return await real_windows_spawn(job, *args)

        monkeypatch.setattr(
            windows_spawn_module,
            "create_windows_job_subprocess_exec",
            controlled_windows_spawn,
        )
    else:
        real_posix_spawn = asyncio.create_subprocess_exec

        async def controlled_posix_spawn(
            *args: str,
            **kwargs: Any,
        ) -> asyncio.subprocess.Process:
            nonlocal spawn_count
            spawn_count += 1
            spawn_entered.set()
            await allow_spawn.wait()
            return await real_posix_spawn(*args, **kwargs)

        monkeypatch.setattr(asyncio, "create_subprocess_exec", controlled_posix_spawn)

    try:
        start_task = asyncio.create_task(
            supervisor.start("project_stop_start_race", "tests.fixtures.silent_worker")
        )
        await asyncio.wait_for(spawn_entered.wait(), timeout=1.0)
        stop_all_task = asyncio.create_task(supervisor.stop_all())
        await asyncio.sleep(0)

        assert stop_all_task.done() is False
        if cancel_stop_all:
            stop_all_task.cancel()
            await asyncio.sleep(0)
            assert stop_all_task.done() is False
        late_start_task = asyncio.create_task(
            supervisor.start("project_after_stop_started", "tests.fixtures.silent_worker")
        )
        await asyncio.sleep(0)

        allow_spawn.set()
        handle = await start_task
        with pytest.raises(WorkerUnavailableError, match="supervisor is unavailable"):
            await late_start_task
        if cancel_stop_all:
            with pytest.raises(asyncio.CancelledError):
                await stop_all_task
        else:
            await stop_all_task

        assert spawn_count == 1
        assert handle.process.returncode is not None
        assert supervisor.get(handle.worker_id) is None
        assert supervisor._workers == {}
        assert supervisor._projects == {}
    finally:
        allow_spawn.set()
        if handle is None and start_task is not None:
            start_result = await asyncio.gather(start_task, return_exceptions=True)
            if isinstance(start_result[0], WorkerHandle):
                handle = start_result[0]
        if late_start_task is not None:
            await asyncio.gather(late_start_task, return_exceptions=True)
        if stop_all_task is not None:
            await asyncio.gather(stop_all_task, return_exceptions=True)
        await asyncio.gather(supervisor.stop_all(), return_exceptions=True)
        if handle is not None:
            await _terminate_process(handle.process)


async def test_start_is_rejected_after_stop_all_before_allocating_worker_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supervisor = WorkerSupervisor(heartbeat_timeout=timedelta(seconds=10))
    allocation_attempted = False

    def unexpected_worker_id(_: str) -> str:
        nonlocal allocation_attempted
        allocation_attempted = True
        raise AssertionError("worker allocation started after supervisor shutdown")

    monkeypatch.setattr(supervisor_module, "new_id", unexpected_worker_id)

    await supervisor.stop_all()

    with pytest.raises(WorkerUnavailableError, match="supervisor is unavailable"):
        await supervisor.start("project_after_stop_all")

    assert allocation_attempted is False
    assert supervisor._workers == {}
    assert supervisor._projects == {}


async def test_stop_all_waits_for_every_stop_task_before_propagating_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        shutdown_timeout_seconds=0.1,
    )
    handles: list[WorkerHandle] = []
    stop_all_task: asyncio.Task[None] | None = None
    first_failed = asyncio.Event()
    second_started = asyncio.Event()
    allow_second = asyncio.Event()
    second_finished = asyncio.Event()
    original_cause = OSError("original-cause-secret")
    original_context = ValueError("original-context-secret")
    primary_error = RuntimeError("worker stop failed")
    primary_error.__cause__ = original_cause
    primary_error.__context__ = original_context
    primary_error.__suppress_context__ = True
    secondary_error = LookupError("secondary-stop-secret")
    original_stop_handle = supervisor._stop_handle

    async def controlled_stop_handle(
        handle: WorkerHandle,
        *,
        graceful: bool,
    ) -> None:
        if handle is handles[0]:
            await original_stop_handle(handle, graceful=graceful)
            first_failed.set()
            raise primary_error
        second_started.set()
        await allow_second.wait()
        await original_stop_handle(handle, graceful=graceful)
        second_finished.set()
        raise secondary_error

    try:
        handles.append(
            await supervisor.start("project_stop_error_1", "tests.fixtures.silent_worker")
        )
        handles.append(
            await supervisor.start("project_stop_error_2", "tests.fixtures.silent_worker")
        )
        monkeypatch.setattr(supervisor, "_stop_handle", controlled_stop_handle)
        stop_all_task = asyncio.create_task(supervisor.stop_all())
        await asyncio.wait_for(
            asyncio.gather(first_failed.wait(), second_started.wait()),
            timeout=2.0,
        )

        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(stop_all_task), timeout=0.05)

        allow_second.set()
        with pytest.raises(RuntimeError, match="worker stop failed") as raised:
            await stop_all_task

        assert second_finished.is_set()
        assert all(handle.process.returncode is not None for handle in handles)
        assert raised.value is primary_error
        assert raised.value.__cause__ is original_cause
        assert raised.value.__context__ is original_context
        assert raised.value.__suppress_context__ is True
        assert raised.value.__notes__ == ["Additional worker cleanup failure occurred."]
        assert "secondary-stop-secret" not in raised.value.__notes__[0]
    finally:
        allow_second.set()
        if stop_all_task is not None:
            await asyncio.gather(stop_all_task, return_exceptions=True)
        await asyncio.gather(supervisor.stop_all(), return_exceptions=True)
        for handle in handles:
            await _terminate_process(handle.process)


async def test_pending_failure_still_schedules_and_waits_for_every_worker_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        shutdown_timeout_seconds=0.1,
    )
    handles: list[WorkerHandle] = []
    identities: tuple[_ProcessIdentity, ...] = ()
    pending: list[asyncio.Future[IpcMessage]] = []
    real_fail_pending = supervisor._fail_pending
    injected = False

    def fail_pending_once(handle: WorkerHandle, error: WorkerError) -> None:
        nonlocal injected
        if not injected:
            injected = True
            raise RuntimeError("pending cleanup failed")
        real_fail_pending(handle, error)

    try:
        handles.append(
            await supervisor.start("project_pending_failure_1", "tests.fixtures.silent_worker")
        )
        handles.append(
            await supervisor.start("project_pending_failure_2", "tests.fixtures.silent_worker")
        )
        identities = tuple(
            _capture_process_identity(f"worker {index}", handle.process.pid)
            for index, handle in enumerate(handles, start=1)
        )
        pending = [asyncio.get_running_loop().create_future() for _ in handles]
        for index, handle in enumerate(handles):
            handle.pending[f"pending-failure-{index}"] = pending[index]
        monkeypatch.setattr(supervisor, "_fail_pending", fail_pending_once)

        with pytest.raises(RuntimeError, match="pending cleanup failed"):
            await supervisor.stop_all()

        assert await _wait_for_identity_exit(identities) == ()
        assert all(handle.process.returncode is not None for handle in handles)
        assert all(handle._stop_task is not None for handle in handles)
        assert all(handle._stop_task.done() for handle in handles if handle._stop_task)
        assert all(isinstance(future.exception(), WorkerUnavailableError) for future in pending)
        assert supervisor._workers == {}
        assert supervisor._projects == {}
    finally:
        for future in pending:
            if future.done():
                future.exception()
        await asyncio.to_thread(_kill_process_identities, identities)
        await asyncio.gather(supervisor.stop_all(), return_exceptions=True)
        for future in pending:
            if future.done():
                future.exception()
        for handle in handles:
            if handle.job is not None:
                await asyncio.to_thread(handle.job.close)
            await _terminate_process(handle.process)


async def test_stop_task_creation_failure_uses_fallback_and_cleans_every_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        shutdown_timeout_seconds=0.1,
    )
    handles: list[WorkerHandle] = []
    identities: tuple[_ProcessIdentity, ...] = ()
    loop = asyncio.get_running_loop()
    real_create_task = loop.create_task
    injected = False

    def fail_create_task_once(
        coroutine: Coroutine[object, object, None],
        *,
        name: str | None = None,
        context: contextvars.Context | None = None,
    ) -> asyncio.Task[None]:
        nonlocal injected
        coroutine_name = getattr(
            getattr(coroutine, "cr_code", None),
            "co_name",
            None,
        )
        if not injected and coroutine_name == "_run_stop_task":
            injected = True
            coroutine.close()
            raise RuntimeError("stop task creation failed")
        return real_create_task(coroutine, name=name, context=context)

    try:
        handles.append(
            await supervisor.start("project_task_failure_1", "tests.fixtures.silent_worker")
        )
        handles.append(
            await supervisor.start("project_task_failure_2", "tests.fixtures.silent_worker")
        )
        identities = tuple(
            _capture_process_identity(f"worker {index}", handle.process.pid)
            for index, handle in enumerate(handles, start=1)
        )
        monkeypatch.setattr(loop, "create_task", fail_create_task_once)

        with pytest.raises(RuntimeError, match="stop task creation failed"):
            await supervisor.stop_all()

        assert await _wait_for_identity_exit(identities) == ()
        assert all(handle.process.returncode is not None for handle in handles)
        assert all(handle._stop_task is not None for handle in handles)
        assert all(handle._stop_task.done() for handle in handles if handle._stop_task)
        assert all(handle.job is None or handle.job._handle is None for handle in handles)
        assert supervisor._workers == {}
        assert supervisor._projects == {}
    finally:
        await asyncio.to_thread(_kill_process_identities, identities)
        await asyncio.gather(supervisor.stop_all(), return_exceptions=True)
        for handle in handles:
            if handle.job is not None:
                await asyncio.to_thread(handle.job.close)
            await _terminate_process(handle.process)


async def test_cleanup_task_runtime_error_is_propagated_after_full_cleanup() -> None:
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        shutdown_timeout_seconds=0.1,
    )
    handle = await supervisor.start(
        "project_cleanup_task_failure",
        "tests.fixtures.silent_worker",
    )
    identity = _capture_process_identity("worker", handle.process.pid)
    original_stderr_task = handle._stderr_task
    original_stderr_task.cancel()
    await asyncio.gather(original_stderr_task, return_exceptions=True)
    cleanup_task_started = asyncio.Event()

    async def fail_when_cancelled() -> None:
        cleanup_task_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise RuntimeError("stderr task cleanup failed") from None

    handle._stderr_task = asyncio.create_task(fail_when_cancelled())
    await asyncio.wait_for(cleanup_task_started.wait(), timeout=1.0)

    try:
        with pytest.raises(RuntimeError, match="stderr task cleanup failed"):
            await supervisor.stop_all()

        assert handle.process.returncode is not None
        assert await _wait_for_identity_exit((identity,)) == ()
        assert handle.job is None or handle.job._handle is None
        assert handle.reader_task.done()
        assert handle._stderr_task.done()
        assert supervisor._workers == {}
        assert supervisor._projects == {}
    finally:
        await asyncio.to_thread(_kill_process_identities, (identity,))
        await asyncio.gather(supervisor.stop_all(), return_exceptions=True)
        if handle.job is not None:
            await asyncio.to_thread(handle.job.close)
        handle.reader_task.cancel()
        handle._stderr_task.cancel()
        await asyncio.gather(
            handle.reader_task,
            handle._stderr_task,
            return_exceptions=True,
        )
        await _terminate_process(handle.process)


async def test_pending_future_failure_does_not_strand_later_futures() -> None:
    class FailingSetExceptionFuture(asyncio.Future[IpcMessage]):
        def set_exception(
            self,
            exception: type[BaseException] | BaseException,
            /,
        ) -> None:
            del exception
            raise RuntimeError("future notification failed")

    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        shutdown_timeout_seconds=0.1,
    )
    handle = await supervisor.start(
        "project_future_notification_failure",
        "tests.fixtures.silent_worker",
    )
    identity = _capture_process_identity("worker", handle.process.pid)
    failing_future = FailingSetExceptionFuture()
    later_future: asyncio.Future[IpcMessage] = asyncio.get_running_loop().create_future()
    handle.pending["failing-future"] = failing_future
    handle.pending["later-future"] = later_future

    try:
        with pytest.raises(RuntimeError, match="future notification failed"):
            await supervisor.stop_all()

        assert failing_future.cancelled()
        assert isinstance(later_future.exception(), WorkerUnavailableError)
        assert handle.pending == {}
        assert handle.process.returncode is not None
        assert await _wait_for_identity_exit((identity,)) == ()
        assert handle.job is None or handle.job._handle is None
        assert handle.reader_task.done()
        assert handle._stderr_task.done()
        assert supervisor._workers == {}
        assert supervisor._projects == {}
    finally:
        for future in (failing_future, later_future):
            if not future.done():
                future.cancel()
            if future.done() and not future.cancelled():
                future.exception()
        await asyncio.to_thread(_kill_process_identities, (identity,))
        await asyncio.gather(supervisor.stop_all(), return_exceptions=True)
        if handle.job is not None:
            await asyncio.to_thread(handle.job.close)
        await _terminate_process(handle.process)


async def test_reader_pending_failure_still_completes_full_worker_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        shutdown_timeout_seconds=0.1,
    )
    handle: WorkerHandle | None = None
    identity: _ProcessIdentity | None = None
    send_task: asyncio.Task[IpcMessage] | None = None
    try:
        handle = await supervisor.start(
            "project_reader_pending_failure",
            "tests.fixtures.corrupt_worker",
        )
        identity = _capture_process_identity("worker", handle.process.pid)
        real_fail_pending = supervisor._fail_pending
        fail_pending_calls = 0

        def fail_pending_once(handle: WorkerHandle, error: WorkerError) -> None:
            nonlocal fail_pending_calls
            fail_pending_calls += 1
            if fail_pending_calls == 1:
                raise RuntimeError("reader pending cleanup failed")
            real_fail_pending(handle, error)

        monkeypatch.setattr(supervisor, "_fail_pending", fail_pending_once)
        send_task = asyncio.create_task(
            supervisor.send(
                handle.worker_id,
                "command",
                {"name": "trigger_corruption"},
                timeout_seconds=2.0,
            )
        )

        with pytest.raises(RuntimeError, match="reader pending cleanup failed"):
            await asyncio.wait_for(handle.reader_task, timeout=3.0)

        assert handle.process.returncode is not None
        assert identity is not None
        assert await _wait_for_identity_exit((identity,)) == ()
        assert handle.job is None or handle.job._handle is None
        assert handle._stderr_task.done()
        assert send_task is not None
        with pytest.raises(WorkerUnavailableError, match="worker is unavailable"):
            await send_task
        assert handle.pending == {}
        assert supervisor._workers == {}
        assert supervisor._projects == {}
    finally:
        if send_task is not None:
            if not send_task.done():
                send_task.cancel()
            await asyncio.gather(send_task, return_exceptions=True)
        if identity is not None:
            await asyncio.to_thread(_kill_process_identities, (identity,))
        await asyncio.gather(supervisor.stop_all(), return_exceptions=True)
        if handle is not None:
            if handle.job is not None:
                await asyncio.to_thread(handle.job.close)
            handle._stderr_task.cancel()
            await asyncio.gather(handle._stderr_task, return_exceptions=True)
            await _terminate_process(handle.process)


async def test_stop_all_capture_failure_still_completes_full_worker_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        shutdown_timeout_seconds=0.1,
    )
    project_id = f"capture_failure_{uuid4().hex}"
    pid_path = _child_pid_path(project_id)
    pid_path.unlink(missing_ok=True)
    handle: WorkerHandle | None = None
    child_pid: int | None = None
    identities: tuple[_ProcessIdentity, ...] = ()
    pending: asyncio.Future[IpcMessage] | None = None
    capture_error = RuntimeError("descendant capture failed")
    capture_cause = OSError("capture-cause-secret")
    capture_context = ValueError("capture-context-secret")
    capture_error.__cause__ = capture_cause
    capture_error.__context__ = capture_context
    capture_error.__suppress_context__ = True
    close_error = LookupError("close-job-secret")

    def fail_capture(_: int) -> list[object]:
        raise capture_error

    async def fail_remove_registry(_: WorkerHandle) -> None:
        raise close_error

    try:
        handle = await supervisor.start(project_id, "tests.fixtures.child_worker")
        child_pid = await _wait_for_child_pid(pid_path)
        identities = (
            _capture_process_identity("worker", handle.process.pid),
            _capture_process_identity("worker child", child_pid),
        )
        pending = asyncio.get_running_loop().create_future()
        handle.pending["capture-failure-pending"] = pending
        monkeypatch.setattr(supervisor_module, "_capture_descendants_sync", fail_capture)
        monkeypatch.setattr(supervisor, "_remove_registry", fail_remove_registry)

        with pytest.raises(RuntimeError, match="descendant capture failed") as raised:
            await supervisor.stop_all()

        assert handle.process.returncode is not None
        assert await _wait_for_identity_exit(identities) == ()
        assert handle.job is None or handle.job._handle is None
        assert handle.reader_task.done()
        assert handle._stderr_task.done()
        assert isinstance(pending.exception(), WorkerUnavailableError)
        assert handle.pending == {}
        assert supervisor._workers == {}
        assert supervisor._projects == {}
        assert raised.value is capture_error
        assert raised.value.__cause__ is capture_cause
        assert raised.value.__context__ is capture_context
        assert raised.value.__suppress_context__ is True
        assert raised.value.__notes__ == ["Additional worker cleanup failure occurred."]
        assert "close-job-secret" not in raised.value.__notes__[0]
    finally:
        if pending is not None and pending.done():
            pending.exception()
        await asyncio.gather(supervisor.stop_all(), return_exceptions=True)
        await asyncio.to_thread(_kill_process_identities, identities)
        if handle is not None:
            if handle.job is not None:
                await asyncio.to_thread(handle.job.close)
            handle.reader_task.cancel()
            handle._stderr_task.cancel()
            await asyncio.gather(
                handle.reader_task,
                handle._stderr_task,
                return_exceptions=True,
            )
            await _terminate_process(handle.process)
        if child_pid is not None:
            await asyncio.to_thread(_kill_pid_if_alive, child_pid)
        pid_path.unlink(missing_ok=True)


async def test_unexpected_shutdown_request_failure_still_completes_full_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        shutdown_timeout_seconds=0.1,
    )
    project_id = f"request_failure_{uuid4().hex}"
    pid_path = _child_pid_path(project_id)
    pid_path.unlink(missing_ok=True)
    handle: WorkerHandle | None = None
    child_pid: int | None = None
    identities: tuple[_ProcessIdentity, ...] = ()
    pending: asyncio.Future[IpcMessage] | None = None
    detached_job: WindowsJob | None = None

    async def fail_shutdown_request(*_: object, **__: object) -> None:
        raise RuntimeError("shutdown request failed")

    try:
        handle = await supervisor.start(project_id, "tests.fixtures.child_worker")
        child_pid = await _wait_for_child_pid(pid_path)
        identities = (
            _capture_process_identity("worker", handle.process.pid),
            _capture_process_identity("worker child", child_pid),
        )
        pending = asyncio.get_running_loop().create_future()
        handle.pending["request-failure-pending"] = pending
        detached_job = handle.job
        handle.job = None
        monkeypatch.setattr(supervisor, "_request", fail_shutdown_request)

        with pytest.raises(RuntimeError, match="shutdown request failed"):
            await supervisor.stop_all()

        assert handle.process.returncode is not None
        assert await _wait_for_identity_exit(identities) == ()
        assert handle.reader_task.done()
        assert handle._stderr_task.done()
        assert isinstance(pending.exception(), WorkerUnavailableError)
        assert handle.pending == {}
        assert supervisor._workers == {}
        assert supervisor._projects == {}
    finally:
        if pending is not None and pending.done():
            pending.exception()
        await asyncio.gather(supervisor.stop_all(), return_exceptions=True)
        await asyncio.to_thread(_kill_process_identities, identities)
        if detached_job is not None:
            await asyncio.to_thread(detached_job.close)
        if handle is not None:
            if detached_job is None and handle.job is not None:
                await asyncio.to_thread(handle.job.close)
            handle.reader_task.cancel()
            handle._stderr_task.cancel()
            await asyncio.gather(
                handle.reader_task,
                handle._stderr_task,
                return_exceptions=True,
            )
            await _terminate_process(handle.process)
        if child_pid is not None:
            await asyncio.to_thread(_kill_pid_if_alive, child_pid)
        pid_path.unlink(missing_ok=True)


async def test_process_tree_failure_uses_direct_process_kill_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supervisor = WorkerSupervisor(heartbeat_timeout=timedelta(seconds=10))
    handle = await supervisor.start(
        "project_tree_fallback",
        "tests.fixtures.silent_worker",
    )

    def fail_tree_termination(_: int) -> None:
        raise RuntimeError("psutil tree termination failed")

    monkeypatch.setattr(
        supervisor_module,
        "_terminate_process_tree_sync",
        fail_tree_termination,
    )

    try:
        with pytest.raises(RuntimeError, match="psutil tree termination failed"):
            await supervisor._terminate_process_tree(handle.process)

        assert handle.process.returncode is not None
    finally:
        await asyncio.gather(supervisor.stop_all(), return_exceptions=True)
        if handle.job is not None:
            await asyncio.to_thread(handle.job.close)
        await _terminate_process(handle.process)


@pytest.mark.skipif(os.name != "nt", reason="Windows Job close failure only")
async def test_job_close_oserror_is_propagated_after_retry_closes_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        shutdown_timeout_seconds=0.1,
    )
    handle = await supervisor.start(
        "project_job_close_failure",
        "tests.fixtures.silent_worker",
    )
    job = handle.job
    assert job is not None
    real_close = job.close
    close_attempted = False

    def fail_job_close() -> None:
        nonlocal close_attempted
        close_attempted = True
        raise OSError("job close failed")

    monkeypatch.setattr(job, "close", fail_job_close)

    try:
        with pytest.raises(OSError, match="job close failed"):
            await supervisor.stop_all()

        assert close_attempted is True
        assert job._handle is None
        assert handle.process.returncode is not None
        assert handle.reader_task.done()
        assert handle._stderr_task.done()
        assert supervisor._workers == {}
        assert supervisor._projects == {}
    finally:
        await asyncio.to_thread(real_close)
        await _terminate_process(handle.process)


async def test_registry_removal_failure_uses_locked_direct_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        shutdown_timeout_seconds=0.1,
    )
    handle = await supervisor.start(
        "project_registry_failure",
        "tests.fixtures.silent_worker",
    )

    async def fail_registry_removal(_: WorkerHandle) -> None:
        raise RuntimeError("registry removal failed")

    async def fail_registry_helper(_: WorkerHandle) -> None:
        raise RuntimeError("registry helper failed")

    monkeypatch.setattr(supervisor, "_remove_registry", fail_registry_removal)
    monkeypatch.setattr(supervisor, "_remove_registry_entries", fail_registry_helper)

    try:
        with pytest.raises(RuntimeError, match="registry removal failed"):
            await supervisor.stop_all()

        assert handle.process.returncode is not None
        assert handle.reader_task.done()
        assert handle._stderr_task.done()
        assert supervisor._workers == {}
        assert supervisor._projects == {}
    finally:
        async with supervisor._registry_lock:
            supervisor._workers.clear()
            supervisor._projects.clear()
        if handle.job is not None:
            await asyncio.to_thread(handle.job.close)
        await _terminate_process(handle.process)


async def test_broken_worker_stdin_raises_sanitized_unavailable_and_cleans_up() -> None:
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        shutdown_timeout_seconds=0.1,
    )
    handle = await supervisor.start(
        "project_broken_stdin",
        "tests.fixtures.broken_stdin_worker",
    )
    started_at = handle.last_heartbeat_at

    try:
        for _ in range(200):
            if handle.last_heartbeat_at > started_at:
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("broken-stdin fixture did not become ready")

        with pytest.raises(WorkerUnavailableError, match="worker is unavailable"):
            await supervisor.send(
                handle.worker_id,
                "command",
                {"secret": "DO_NOT_ECHO_BROKEN_PIPE"},
                timeout_seconds=1.0,
            )

        assert handle.pending == {}
        assert handle.process.returncode is not None
        assert supervisor.get(handle.worker_id) is None
    finally:
        await supervisor.stop_all()
        await _terminate_process(handle.process)


async def test_stderr_flood_does_not_block_ping_or_shutdown() -> None:
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        response_timeout_seconds=2.0,
    )
    handle = await supervisor.start(
        "project_stderr_flood",
        "tests.fixtures.stderr_flood_worker",
    )

    try:
        assert (await supervisor.ping(handle.worker_id)).payload == {"status": "ok"}
        await supervisor.stop(handle.worker_id)
        assert handle.process.returncode == 0
    finally:
        await supervisor.stop_all()
        await _terminate_process(handle.process)


async def test_stderr_flood_persists_only_opaque_evidence(tmp_path: Path) -> None:
    runtime = configure_logging(
        tmp_path / "logs",
        "INFO",
        max_bytes=64 * 1024,
        max_record_bytes=4096,
        retained_file_count=2,
        retention_age=timedelta(days=1),
        queue_capacity=128,
        shutdown_drain_timeout=timedelta(seconds=1),
    )
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        response_timeout_seconds=2.0,
    )
    handle = await supervisor.start(
        "project_stderr_evidence",
        "tests.fixtures.stderr_flood_worker",
    )
    try:
        assert (await supervisor.ping(handle.worker_id)).payload == {"status": "ok"}
        await supervisor.stop(handle.worker_id)
    finally:
        await supervisor.stop_all()
        await _terminate_process(handle.process)
        runtime.close()

    raw = b"x" * (2 * 1024 * 1024)
    log_bytes = (tmp_path / "logs" / "backend.jsonl").read_bytes()
    assert raw[:4096] not in log_bytes
    events = [json.loads(line) for line in log_bytes.splitlines()]
    opaque = next(event for event in events if event["event"] == "worker_stderr_opaque")
    assert opaque["byte_count"] == len(raw)
    assert opaque["sha256"] == hashlib.sha256(raw).hexdigest()
    assert opaque["worker_id"] == handle.worker_id
    assert opaque["project_id"] == "project_stderr_evidence"


async def test_stop_on_broken_stdin_does_not_await_its_own_cleanup() -> None:
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        shutdown_timeout_seconds=0.1,
    )
    handle = await supervisor.start(
        "project_stop_broken_stdin",
        "tests.fixtures.broken_stdin_worker",
    )
    started_at = handle.last_heartbeat_at

    try:
        for _ in range(200):
            if handle.last_heartbeat_at > started_at:
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("broken-stdin fixture did not become ready")

        await asyncio.wait_for(supervisor.stop(handle.worker_id), timeout=1.0)

        assert handle.process.returncode is not None
        assert supervisor.get(handle.worker_id) is None
    finally:
        await _terminate_process(handle.process)


@pytest.mark.skipif(os.name == "nt", reason="POSIX process group containment only")
async def test_graceful_stop_cleans_posix_group_after_parent_exits_zero() -> None:
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        shutdown_timeout_seconds=0.1,
    )
    project_id = f"graceful_tree_{uuid4().hex}"
    pid_path = _child_pid_path(project_id)
    pid_path.unlink(missing_ok=True)
    handle = await supervisor.start(project_id, "tests.fixtures.shutdown_child_worker")
    started_at = handle.last_heartbeat_at
    child_pid: int | None = None

    try:
        for _ in range(200):
            if handle.last_heartbeat_at > started_at:
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("shutdown-child fixture did not become ready")

        await supervisor.stop(handle.worker_id)
        child_pid = await _wait_for_child_pid(pid_path)

        assert handle.process.returncode == 0
        await _wait_for_pid_exit(child_pid)
    finally:
        await supervisor.stop_all()
        await _terminate_process(handle.process)
        if child_pid is not None:
            await asyncio.to_thread(_kill_pid_if_alive, child_pid)
        pid_path.unlink(missing_ok=True)


async def test_unexpected_stdout_eof_cleans_parent_and_child() -> None:
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        shutdown_timeout_seconds=0.1,
    )
    project_id = f"eof_tree_{uuid4().hex}"
    pid_path = _child_pid_path(project_id)
    pid_path.unlink(missing_ok=True)
    handle = await supervisor.start(project_id, "tests.fixtures.eof_child_worker")
    child_pid: int | None = None

    try:
        child_pid = await _wait_for_child_pid(pid_path)

        await asyncio.wait_for(handle.reader_task, timeout=2.0)

        assert supervisor.get(handle.worker_id) is None
        assert handle.process.returncode is not None
        await _wait_for_pid_exit(child_pid)
    finally:
        await supervisor.stop_all()
        await _terminate_process(handle.process)
        if child_pid is not None:
            await asyncio.to_thread(_kill_pid_if_alive, child_pid)
        pid_path.unlink(missing_ok=True)


@pytest.mark.skipif(os.name != "nt", reason="Windows atomic spawn only")
async def test_start_failure_after_spawn_reaps_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spawned: list[asyncio.subprocess.Process] = []
    real_spawn = windows_spawn_module.create_windows_job_subprocess_exec

    async def recording_spawn(
        job: WindowsJob,
        *args: str,
    ) -> asyncio.subprocess.Process:
        process = await real_spawn(job, *args)
        spawned.append(process)
        return process

    def broken_clock() -> datetime:
        raise RuntimeError("SECRET_CLOCK_FAILURE")

    monkeypatch.setattr(
        windows_spawn_module,
        "create_windows_job_subprocess_exec",
        recording_spawn,
    )
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        clock=broken_clock,
    )

    try:
        with pytest.raises(WorkerUnavailableError, match="could not be started"):
            await supervisor.start("project_partial_start", "tests.fixtures.silent_worker")

        assert len(spawned) == 1
        assert spawned[0].returncode is not None
    finally:
        for process in spawned:
            await _terminate_process(process)


@pytest.mark.skipif(os.name == "nt", reason="POSIX process group containment only")
async def test_posix_start_failure_reaps_process_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = f"posix_partial_start_{uuid4().hex}"
    pid_path = _child_pid_path(project_id)
    pid_path.unlink(missing_ok=True)
    identities: list[_ProcessIdentity] = []
    spawned: list[asyncio.subprocess.Process] = []
    real_spawn = asyncio.create_subprocess_exec
    real_group_cleanup = WorkerSupervisor._terminate_posix_process_group

    async def recording_spawn(
        *args: str,
        **kwargs: Any,
    ) -> asyncio.subprocess.Process:
        process = await real_spawn(*args, **kwargs)
        spawned.append(process)
        identities.append(_capture_process_identity("worker", process.pid))
        return process

    async def cleanup_group_then_fail(
        process_group_id: int,
        process_id: int,
    ) -> None:
        await real_group_cleanup(process_group_id, process_id)
        raise RuntimeError("cleanup-secret")

    def broken_clock() -> datetime:
        for _ in range(200):
            raw_child_pid = _read_text_if_present(pid_path)
            if raw_child_pid is not None:
                identities.append(_capture_process_identity("worker child", int(raw_child_pid)))
                raise RuntimeError("clock failed")
            time.sleep(0.01)
        raise AssertionError("child PID fixture was not published")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", recording_spawn)
    monkeypatch.setattr(
        WorkerSupervisor,
        "_terminate_posix_process_group",
        staticmethod(cleanup_group_then_fail),
    )
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        clock=broken_clock,
    )

    try:
        with pytest.raises(WorkerUnavailableError, match="could not be started") as raised:
            await supervisor.start(project_id, "tests.fixtures.immediate_child_worker")

        assert len(identities) == 2
        assert await _wait_for_identity_exit(tuple(identities)) == ()
        assert raised.value.__notes__ == ["Additional worker cleanup failure occurred."]
        assert "RuntimeError" not in raised.value.__notes__[0]
        assert "cleanup-secret" not in raised.value.__notes__[0]
    finally:
        await asyncio.to_thread(_kill_process_identities, tuple(identities))
        for process in spawned:
            await _terminate_process(process)
        pid_path.unlink(missing_ok=True)


@pytest.mark.skipif(os.name != "nt", reason="Windows Job containment only")
async def test_immediate_child_is_in_exact_job_and_dies_when_job_closes() -> None:
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        shutdown_timeout_seconds=0.1,
    )
    project_id = f"exact_job_{uuid4().hex}"
    pid_path = _child_pid_path(project_id)
    pid_path.unlink(missing_ok=True)
    handle = await supervisor.start(project_id, "tests.fixtures.immediate_child_worker")
    child_pid: int | None = None

    try:
        child_pid = await _wait_for_child_pid(pid_path)
        assert handle.job is not None
        assert handle.job.contains_process(handle.process.pid)
        assert handle.job.contains_process(child_pid)

        await asyncio.to_thread(handle.job.close)

        await _wait_for_pid_exit(child_pid)
        await asyncio.wait_for(handle.process.wait(), timeout=2.0)
        assert handle.job._handle is None
    finally:
        await supervisor.stop_all()
        await _terminate_process(handle.process)
        if child_pid is not None:
            await asyncio.to_thread(_kill_pid_if_alive, child_pid)
        pid_path.unlink(missing_ok=True)


@pytest.mark.skipif(os.name != "nt", reason="Windows atomic Job startup only")
async def test_real_venv_launcher_chain_is_atomically_contained_by_job() -> None:
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        shutdown_timeout_seconds=0.1,
    )
    project_id = f"atomic_job_chain_{uuid4().hex}"
    target_path, child_interpreter_path = atomic_job_chain_paths(project_id)
    target_path.unlink(missing_ok=True)
    child_interpreter_path.unlink(missing_ok=True)
    handle = None
    identities: tuple[_ProcessIdentity, ...] = ()

    try:
        handle = await supervisor.start(project_id, "tests.fixtures.atomic_job_chain_worker")
        target_pid, child_launcher_pid = await _wait_for_pid_pair(target_path)
        child_interpreter_pid = await _wait_for_child_pid(child_interpreter_path)
        identities = (
            _capture_process_identity("supervisor launcher", handle.process.pid),
            _capture_process_identity("bootstrap interpreter", target_pid),
            _capture_process_identity("immediate child launcher", child_launcher_pid),
            _capture_process_identity("immediate child interpreter", child_interpreter_pid),
        )
        assert len({identity.pid for identity in identities}) == 4
        assert handle.process.stdin is not None
        assert not handle.process.stdin.is_closing()
        assert handle.job is not None
        membership = {
            identity.role: handle.job.contains_process(identity.pid) for identity in identities
        }

        await asyncio.to_thread(handle.job.close)

        survivors = await _wait_for_identity_exit(identities)
        assert not survivors, (
            f"processes escaped direct Job close: membership={membership}, survivors={survivors}"
        )
        assert all(membership.values()), f"processes were never in the exact Job: {membership}"
    finally:
        if identities:
            await asyncio.to_thread(_kill_process_identities, identities)
        await supervisor.stop_all()
        if handle is not None and handle.process.returncode is None:
            await _terminate_process(handle.process)
        target_path.unlink(missing_ok=True)
        child_interpreter_path.unlink(missing_ok=True)


@pytest.mark.skipif(os.name != "nt", reason="Windows Job containment only")
async def test_atomic_spawn_denial_is_sanitized_and_closes_start_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jobs: list[WindowsJob] = []
    gates: list[WindowsStartGate] = []
    real_job_create = WindowsJob.create
    real_gate_create = WindowsStartGate.create

    async def denied_spawn(job: WindowsJob, *args: str) -> asyncio.subprocess.Process:
        del job, args
        raise ctypes.WinError(5)

    def recording_job_create(cls: type[WindowsJob]) -> WindowsJob:
        del cls
        job = real_job_create()
        jobs.append(job)
        return job

    def recording_gate_create(cls: type[WindowsStartGate]) -> WindowsStartGate:
        del cls
        gate = real_gate_create()
        gates.append(gate)
        return gate

    monkeypatch.setattr(
        windows_spawn_module,
        "create_windows_job_subprocess_exec",
        denied_spawn,
    )
    monkeypatch.setattr(WindowsJob, "create", classmethod(recording_job_create))
    monkeypatch.setattr(WindowsStartGate, "create", classmethod(recording_gate_create))
    supervisor = WorkerSupervisor(heartbeat_timeout=timedelta(seconds=10))

    try:
        with pytest.raises(WorkerUnavailableError, match="could not be started") as raised:
            await supervisor.start("project_atomic_spawn_denied")
        assert str(raised.value) == "worker could not be started"
    finally:
        await supervisor.stop_all()
    assert len(jobs) == 1
    assert jobs[0]._handle is None
    assert len(gates) == 1
    assert gates[0]._handle is None
    assert gates[0]._ready_handle is None


@pytest.mark.skipif(os.name != "nt", reason="Windows start gate only")
async def test_gate_release_failure_reaps_bootstrap_without_running_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = f"gate_failure_{uuid4().hex}"
    path = _import_marker_path(project_id)
    path.unlink(missing_ok=True)
    spawned: list[asyncio.subprocess.Process] = []
    real_spawn = windows_spawn_module.create_windows_job_subprocess_exec

    async def recording_spawn(
        job: WindowsJob,
        *args: str,
    ) -> asyncio.subprocess.Process:
        process = await real_spawn(job, *args)
        spawned.append(process)
        return process

    def broken_release(self: WindowsStartGate) -> None:
        del self
        raise OSError("SECRET_GATE_RELEASE_FAILURE")

    monkeypatch.setattr(
        windows_spawn_module,
        "create_windows_job_subprocess_exec",
        recording_spawn,
    )
    monkeypatch.setattr(WindowsStartGate, "release", broken_release)
    supervisor = WorkerSupervisor(heartbeat_timeout=timedelta(seconds=10))

    try:
        with pytest.raises(WorkerUnavailableError, match="could not be started"):
            await supervisor.start(project_id, "tests.fixtures.import_marker_worker")

        assert not path.exists()
        assert len(spawned) == 1
        assert spawned[0].returncode is not None
    finally:
        await supervisor.stop_all()
        for process in spawned:
            await _terminate_process(process)
        path.unlink(missing_ok=True)
