import asyncio
import ctypes
import gc
import os
import sys
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import psutil  # type: ignore[import-untyped]
import pytest

import agent_platform.infrastructure.workers.supervisor as supervisor_module
import agent_platform.infrastructure.workers.windows_create_process as create_process_module
import agent_platform.infrastructure.workers.windows_spawn as windows_spawn_module
from agent_platform.infrastructure.workers.supervisor import (
    WorkerSupervisor,
    WorkerUnavailableError,
)
from agent_platform.infrastructure.workers.windows_create_process import CreatedWindowsProcess
from agent_platform.infrastructure.workers.windows_job import WindowsJob
from agent_platform.infrastructure.workers.windows_spawn import (
    create_windows_job_subprocess_exec,
)

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows atomic Job spawn only")


def _process_identity(pid: int) -> tuple[int, float]:
    process = psutil.Process(pid)
    return pid, process.create_time()


def _identity_is_alive(identity: tuple[int, float]) -> bool:
    pid, create_time = identity
    try:
        process = psutil.Process(pid)
        return process.create_time() == create_time and process.is_running()
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
        return False


async def _wait_for_identity_exit(identity: tuple[int, float]) -> None:
    for _ in range(200):
        if not await asyncio.to_thread(_identity_is_alive, identity):
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"atomic spawn left a live process: {identity}")


def _child_identities() -> set[tuple[int, float]]:
    try:
        children = psutil.Process().children(recursive=True)
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
        return set()
    identities: set[tuple[int, float]] = set()
    for child in children:
        try:
            identities.add((child.pid, child.create_time()))
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            pass
    return identities


async def _settle_handles() -> int:
    for _ in range(3):
        await asyncio.sleep(0)
        gc.collect()
    return psutil.Process().num_handles()


async def _round_trip_once() -> None:
    job = WindowsJob.create()
    process = await create_windows_job_subprocess_exec(
        job,
        sys.executable,
        "-c",
        (
            "import sys; data = sys.stdin.buffer.read(); "
            "sys.stdout.buffer.write(data.upper()); "
            "sys.stderr.buffer.write(b'stderr-ok')"
        ),
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(b"round-trip"), timeout=5)
        assert stdout == b"ROUND-TRIP"
        assert stderr == b"stderr-ok"
        assert process.returncode == 0
    finally:
        job.close()
        job.close()
        if process.returncode is None:
            process.kill()
            await process.wait()


async def _assert_sanitized_start_failure(
    supervisor: WorkerSupervisor,
    project_id: str,
) -> None:
    with pytest.raises(WorkerUnavailableError) as raised:
        await supervisor.start(project_id)
    assert str(raised.value) == "worker could not be started"
    assert supervisor._workers == {}
    assert supervisor._projects == {}


async def test_repeated_atomic_spawn_round_trip_has_stable_handle_count() -> None:
    await _round_trip_once()
    baseline = await _settle_handles()

    for _ in range(12):
        await _round_trip_once()

    assert await _settle_handles() <= baseline


def test_windows_command_line_rejects_embedded_nul() -> None:
    with pytest.raises(ValueError, match="command line is invalid"):
        create_process_module._build_command_line((sys.executable, "bad\0argument"))


async def test_real_create_process_failure_is_sanitized_without_leak(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    secret_executable = tmp_path / "SECRET_MISSING_WORKER_EXECUTABLE.exe"
    monkeypatch.setattr(supervisor_module.sys, "executable", str(secret_executable))
    supervisor = WorkerSupervisor(heartbeat_timeout=timedelta(seconds=10))

    for index in range(6):
        await _assert_sanitized_start_failure(supervisor, f"create_failure_warm_{index}")
    baseline_handles = await _settle_handles()
    baseline_children = _child_identities()
    for index in range(8):
        await _assert_sanitized_start_failure(supervisor, f"create_failure_{index}")

    assert _child_identities() <= baseline_children
    assert await _settle_handles() <= baseline_handles


async def test_attribute_list_failure_is_sanitized_without_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel32 = create_process_module._load_process_kernel32()

    def denied_attribute_update(*args: object) -> int:
        del args
        ctypes.set_last_error(5)
        return 0

    monkeypatch.setattr(kernel32, "UpdateProcThreadAttribute", denied_attribute_update)
    supervisor = WorkerSupervisor(heartbeat_timeout=timedelta(seconds=10))

    for index in range(6):
        await _assert_sanitized_start_failure(supervisor, f"attribute_failure_warm_{index}")
    baseline_handles = await _settle_handles()
    baseline_children = _child_identities()
    for index in range(8):
        await _assert_sanitized_start_failure(supervisor, f"attribute_failure_{index}")

    assert _child_identities() <= baseline_children
    assert await _settle_handles() <= baseline_handles


async def test_asyncio_pipe_connection_failure_reaps_process_and_handles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_create_process = windows_spawn_module.create_process_in_job
    identities: list[tuple[int, float]] = []

    def recording_create_process(**kwargs: Any) -> CreatedWindowsProcess:
        created = real_create_process(**kwargs)
        identities.append(_process_identity(created.pid))
        return created

    async def failed_connect_read_pipe(
        protocol_factory: Callable[[], asyncio.Protocol],
        pipe: Any,
    ) -> tuple[asyncio.Transport, asyncio.Protocol]:
        del protocol_factory, pipe
        raise OSError("SECRET_PIPE_CONNECTION_FAILURE")

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(windows_spawn_module, "create_process_in_job", recording_create_process)
    monkeypatch.setattr(loop, "connect_read_pipe", failed_connect_read_pipe)

    async def run_failure() -> tuple[int, float]:
        job = WindowsJob.create()
        before_count = len(identities)
        with pytest.raises(OSError, match="SECRET_PIPE_CONNECTION_FAILURE"):
            await create_windows_job_subprocess_exec(
                job,
                sys.executable,
                "-c",
                "import time; time.sleep(60)",
            )
        assert job._handle is None
        assert len(identities) == before_count + 1
        identity = identities[-1]
        await _wait_for_identity_exit(identity)
        return identity

    for _ in range(4):
        await run_failure()
    for _ in range(6):
        await run_failure()
    first_plateau = await _settle_handles()
    for _ in range(6):
        await run_failure()
    assert await _settle_handles() <= first_plateau


async def test_asyncio_pipe_connection_cancellation_reaps_process_and_handles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_create_process = windows_spawn_module.create_process_in_job
    identities: list[tuple[int, float]] = []

    def recording_create_process(**kwargs: Any) -> CreatedWindowsProcess:
        created = real_create_process(**kwargs)
        identities.append(_process_identity(created.pid))
        return created

    loop = asyncio.get_running_loop()
    real_connect_read_pipe = loop.connect_read_pipe
    monkeypatch.setattr(windows_spawn_module, "create_process_in_job", recording_create_process)

    async def run_cancellation() -> tuple[int, float]:
        connect_started = asyncio.Event()
        release_connect = asyncio.Event()

        async def blocked_connect_read_pipe(
            protocol_factory: Callable[[], asyncio.Protocol],
            pipe: Any,
        ) -> tuple[asyncio.Transport, asyncio.Protocol]:
            connect_started.set()
            await release_connect.wait()
            return await real_connect_read_pipe(protocol_factory, pipe)

        monkeypatch.setattr(loop, "connect_read_pipe", blocked_connect_read_pipe)
        job = WindowsJob.create()
        before_count = len(identities)
        spawn_task = asyncio.create_task(
            create_windows_job_subprocess_exec(
                job,
                sys.executable,
                "-c",
                "import time; time.sleep(60)",
            )
        )
        try:
            await asyncio.wait_for(connect_started.wait(), timeout=2)
            spawn_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(spawn_task, timeout=3)
        finally:
            release_connect.set()
            monkeypatch.setattr(loop, "connect_read_pipe", real_connect_read_pipe)
        assert job._handle is None
        assert len(identities) == before_count + 1
        identity = identities[-1]
        await _wait_for_identity_exit(identity)
        return identity

    for _ in range(2):
        await run_cancellation()
    for _ in range(3):
        await run_cancellation()
    first_plateau = await _settle_handles()
    for _ in range(3):
        await run_cancellation()
    assert await _settle_handles() <= first_plateau


async def test_platform_job_assignment_refusal_fails_closed_and_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel32 = create_process_module._load_process_kernel32()

    def reject_job_assignment(*args: object) -> int:
        del args
        ctypes.set_last_error(5)
        return 0

    await _round_trip_once()
    baseline_handles = await _settle_handles()
    baseline_children = _child_identities()
    monkeypatch.setattr(kernel32, "CreateProcessW", reject_job_assignment)
    supervisor = WorkerSupervisor(heartbeat_timeout=timedelta(seconds=10))

    await _assert_sanitized_start_failure(
        supervisor,
        "SECRET_REJECTED_NESTED_PROJECT",
    )

    assert _child_identities() <= baseline_children
    assert await _settle_handles() <= baseline_handles
