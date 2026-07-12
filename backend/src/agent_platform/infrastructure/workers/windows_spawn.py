"""Import-safe public facade for atomic Windows Job process creation."""

import asyncio
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .windows_job import WindowsJob


async def create_windows_job_subprocess_exec(
    job: "WindowsJob",
    *args: str,
) -> asyncio.subprocess.Process:
    if os.name != "nt":
        raise OSError("atomic Windows worker spawn is unavailable")

    from .windows_spawn_impl import create_windows_job_subprocess_exec

    return await create_windows_job_subprocess_exec(job, *args)
