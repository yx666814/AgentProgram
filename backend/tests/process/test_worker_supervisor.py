import asyncio
import ctypes
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psutil  # type: ignore[import-untyped]
import pytest
from tests.fixtures.atomic_job_chain_worker import atomic_job_chain_paths

from agent_platform.infrastructure.workers.supervisor import (
    WorkerError,
    WorkerHandle,
    WorkerProtocolError,
    WorkerSupervisor,
    WorkerTimeoutError,
    WorkerUnavailableError,
)
from agent_platform.infrastructure.workers.windows_job import WindowsJob, WindowsStartGate

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
        return process.create_time() == identity.create_time and process.is_running()
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
    real_spawn = windows_spawn_module.create_windows_job_subprocess_exec

    async def recording_spawn(
        job: WindowsJob,
        *args: str,
    ) -> asyncio.subprocess.Process:
        spawn_arguments.append(args)
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
        assert (await supervisor.ping(handle.worker_id)).payload == {"status": "ok"}
    finally:
        await supervisor.stop_all()


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
    handles = [
        await supervisor.start("project_cancel_all_1", "tests.fixtures.silent_worker"),
        await supervisor.start("project_cancel_all_2", "tests.fixtures.silent_worker"),
    ]
    stop_all_task = asyncio.create_task(supervisor.stop_all())

    try:
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
        await supervisor.stop_all()
        for handle in handles:
            await _terminate_process(handle.process)


async def test_stop_all_waits_for_every_stop_task_before_propagating_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supervisor = WorkerSupervisor(
        heartbeat_timeout=timedelta(seconds=10),
        shutdown_timeout_seconds=0.1,
    )
    handles = [
        await supervisor.start("project_stop_error_1", "tests.fixtures.silent_worker"),
        await supervisor.start("project_stop_error_2", "tests.fixtures.silent_worker"),
    ]
    first_failed = asyncio.Event()
    second_started = asyncio.Event()
    allow_second = asyncio.Event()
    second_finished = asyncio.Event()
    original_stop_handle = supervisor._stop_handle

    async def controlled_stop_handle(
        handle: WorkerHandle,
        *,
        graceful: bool,
    ) -> None:
        if handle is handles[0]:
            await original_stop_handle(handle, graceful=graceful)
            first_failed.set()
            raise RuntimeError("worker stop failed")
        second_started.set()
        await allow_second.wait()
        await original_stop_handle(handle, graceful=graceful)
        second_finished.set()

    monkeypatch.setattr(supervisor, "_stop_handle", controlled_stop_handle)
    stop_all_task = asyncio.create_task(supervisor.stop_all())

    try:
        await asyncio.wait_for(
            asyncio.gather(first_failed.wait(), second_started.wait()),
            timeout=2.0,
        )

        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(stop_all_task), timeout=0.05)

        allow_second.set()
        with pytest.raises(RuntimeError, match="worker stop failed"):
            await stop_all_task

        assert second_finished.is_set()
        assert all(handle.process.returncode is not None for handle in handles)
    finally:
        allow_second.set()
        await asyncio.gather(supervisor.stop_all(), return_exceptions=True)
        for handle in handles:
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


async def test_graceful_stop_cleans_child_after_parent_exits_zero() -> None:
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
