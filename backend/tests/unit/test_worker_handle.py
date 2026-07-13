import asyncio
from datetime import UTC, datetime
from typing import cast

from agent_platform.infrastructure.workers.supervisor import WorkerHandle
from agent_platform.interfaces.ipc.framing import FrameDecoder


def test_worker_handle_legacy_constructor_defaults_process_group_id() -> None:
    process = cast(asyncio.subprocess.Process, object())

    handle = WorkerHandle(
        "w",
        "p",
        process,
        FrameDecoder(),
        0,
        datetime.now(UTC),
        {},
    )

    assert handle.process_group_id is None
