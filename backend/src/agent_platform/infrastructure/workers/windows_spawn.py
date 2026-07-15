"""Import-safe public facade for atomic Windows Job process creation."""

import asyncio
import os
from collections.abc import Mapping
from pathlib import Path

from .windows_job import WindowsJob


async def create_windows_job_subprocess_exec(
    job: WindowsJob,
    *args: str,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> asyncio.subprocess.Process:
    """Spawn a piped process atomically inside a Windows Job Object."""

    if os.name != "nt":
        raise OSError("atomic Windows worker spawn is unavailable")

    from .windows_spawn_impl import create_windows_job_subprocess_exec

    return await create_windows_job_subprocess_exec(job, *args, cwd=cwd, env=env)
