import asyncio
import gc
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

import psutil  # type: ignore[import-untyped]
import pytest

from agent_platform.infrastructure.workers.windows_job import WindowsJob, WindowsStartGate

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows start gate only")


def _marker_path(project_id: str) -> Path:
    return Path(tempfile.gettempdir()) / f"agent-platform-{project_id}.import.marker"


async def _terminate_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    process.kill()
    await process.wait()


async def test_bootstrap_does_not_import_target_before_gate_release() -> None:
    project_id = f"bootstrap_wait_{uuid4().hex}"
    worker_id = f"worker_{uuid4().hex}"
    path = _marker_path(project_id)
    path.unlink(missing_ok=True)
    gate = WindowsStartGate.create()
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "agent_platform.workers.bootstrap",
        "--start-gate",
        gate.name,
        "--target-module",
        "tests.fixtures.import_marker_worker",
        "--",
        "--project-id",
        project_id,
        "--worker-id",
        worker_id,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        await asyncio.sleep(0.2)
        assert process.returncode is None
        assert not path.exists()

        await asyncio.to_thread(gate.wait_until_opened, 2.0)
        gate.release()
        gate.close()
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5)

        assert process.returncode == 0
        assert stdout == b""
        assert stderr == b""
        assert path.read_text(encoding="ascii") == f"{project_id}|{worker_id}"
    finally:
        gate.close()
        await _terminate_process(process)
        path.unlink(missing_ok=True)


async def test_bootstrap_missing_gate_fails_safely_without_importing_target() -> None:
    project_id = f"bootstrap_missing_{uuid4().hex}"
    path = _marker_path(project_id)
    path.unlink(missing_ok=True)
    missing_gate = f"Local\\AgentPlatformWorkerStart_{uuid4().hex}"
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "agent_platform.workers.bootstrap",
        "--start-gate",
        missing_gate,
        "--target-module",
        "tests.fixtures.import_marker_worker",
        "--",
        "--project-id",
        project_id,
        "--worker-id",
        "worker_missing_gate",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5)

        assert process.returncode == 1
        assert stdout == b""
        assert stderr.splitlines() == [b"worker bootstrap error"]
        assert not path.exists()
        assert project_id.encode() not in stderr
        assert missing_gate.encode() not in stderr
    finally:
        await _terminate_process(process)
        path.unlink(missing_ok=True)


def test_windows_gate_and_job_handles_close_idempotently_without_leak() -> None:
    process = psutil.Process()
    warm_gate = WindowsStartGate.create()
    warm_gate.close()
    warm_job = WindowsJob.create()
    warm_job.close()
    del warm_gate, warm_job
    gc.collect()
    baseline = process.num_handles()
    closed_resources: list[object] = []

    for _ in range(20):
        gate = WindowsStartGate.create()
        gate.release()
        gate.close()
        gate.close()
        job = WindowsJob.create()
        assert not job.contains_process(os.getpid())
        job.close()
        job.close()
        closed_resources.extend((gate, job))

    gc.collect()
    assert process.num_handles() <= baseline
    assert len(closed_resources) == 40


async def test_windows_job_reports_exact_assigned_process_membership() -> None:
    job = WindowsJob.create()
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import time; time.sleep(60)",
        creationflags=subprocess.CREATE_BREAKAWAY_FROM_JOB,
    )

    try:
        job.assign_process(process.pid)

        assert job.contains_process(process.pid)
    finally:
        job.close()
        await asyncio.wait_for(process.wait(), timeout=5)


def test_windows_job_reports_missing_process_as_not_contained() -> None:
    job = WindowsJob.create()

    try:
        assert not job.contains_process(0xFFFFFFFE)
    finally:
        job.close()


def test_windows_job_rejects_membership_query_after_close_without_os_details() -> None:
    job = WindowsJob.create()
    job.close()

    with pytest.raises(OSError) as raised:
        job.contains_process(os.getpid())

    assert str(raised.value) == "Windows Job Object is closed"
