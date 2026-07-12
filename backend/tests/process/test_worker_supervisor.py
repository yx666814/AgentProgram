import asyncio
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psutil
import pytest

from agent_platform.infrastructure.workers.supervisor import (
    WorkerError,
    WorkerProtocolError,
    WorkerSupervisor,
    WorkerTimeoutError,
    WorkerUnavailableError,
)


class _FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, duration: timedelta) -> None:
        self.now += duration


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


async def _wait_for_child_pid(path: Path) -> int:
    for _ in range(200):
        raw_pid = await asyncio.to_thread(_read_text_if_present, path)
        if raw_pid:
            return int(raw_pid)
        await asyncio.sleep(0.01)
    raise AssertionError("child PID fixture was not published")


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
    handle = await supervisor.start(project_id, "tests.fixtures.child_worker")
    child_pid: int | None = None

    try:
        child_pid = await _wait_for_child_pid(pid_path)

        await supervisor.stop(handle.worker_id)

        assert handle.process.returncode == 0
        assert not psutil.pid_exists(child_pid)
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
        assert not psutil.pid_exists(child_pid)
    finally:
        await supervisor.stop_all()
        await _terminate_process(handle.process)
        if child_pid is not None:
            await asyncio.to_thread(_kill_pid_if_alive, child_pid)
        pid_path.unlink(missing_ok=True)


async def test_start_failure_after_spawn_reaps_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spawned: list[asyncio.subprocess.Process] = []
    real_spawn = asyncio.create_subprocess_exec

    async def recording_spawn(*args: object, **kwargs: object) -> asyncio.subprocess.Process:
        process = await real_spawn(*args, **kwargs)  # type: ignore[arg-type]
        spawned.append(process)
        return process

    def broken_clock() -> datetime:
        raise RuntimeError("SECRET_CLOCK_FAILURE")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", recording_spawn)
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
