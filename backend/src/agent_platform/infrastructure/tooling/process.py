from __future__ import annotations

import asyncio
import hashlib
import os
import signal
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from agent_platform.domain.projects import ProjectCommand, ProjectManifest
from agent_platform.domain.shared.errors import DomainError, ErrorCategory
from agent_platform.domain.tooling import ProcessToolResult
from agent_platform.infrastructure.projects.paths import resolve_project_path
from agent_platform.infrastructure.workers.windows_job import WindowsJob


@dataclass(slots=True)
class _ActiveProcess:
    process: asyncio.subprocess.Process
    job: WindowsJob | None


class ToolProcessRegistry:
    def __init__(self) -> None:
        self._active: dict[str, _ActiveProcess] = {}
        self._lock = asyncio.Lock()

    async def register(
        self, call_id: str, process: asyncio.subprocess.Process, job: WindowsJob | None
    ) -> None:
        async with self._lock:
            if call_id in self._active:
                raise RuntimeError("tool process is already registered")
            self._active[call_id] = _ActiveProcess(process=process, job=job)

    async def unregister(self, call_id: str) -> None:
        async with self._lock:
            self._active.pop(call_id, None)

    async def cancel(self, call_id: str) -> bool:
        async with self._lock:
            active = self._active.get(call_id)
        if active is None:
            return False
        await _terminate(active)
        return True

    async def cancel_all(self) -> None:
        async with self._lock:
            active = tuple(self._active.values())
        await asyncio.gather(*(_terminate(item) for item in active), return_exceptions=True)


class ControlledProcessRunner:
    def __init__(self, registry: ToolProcessRegistry, *, max_output_bytes: int) -> None:
        self._registry = registry
        self._max_output_bytes = max_output_bytes

    async def run(
        self,
        call_id: str,
        workspace_root: Path,
        manifest: ProjectManifest,
        *,
        tool_name: str,
        command_index: int,
        timeout_seconds: int,
    ) -> tuple[ProcessToolResult, bytes, bytes]:
        command = _select_command(manifest, tool_name, command_index)
        cwd = workspace_root
        if command.working_directory is not None:
            cwd = resolve_project_path(workspace_root, command.working_directory)
            if not cwd.is_dir():
                raise _invalid("tool.working_directory_invalid", "Working directory is invalid")
        timeout = min(timeout_seconds, command.timeout_seconds)
        process, job = await _spawn(command.argv, cwd)
        await self._registry.register(call_id, process, job)
        try:
            stdout_task = asyncio.create_task(_read_bounded(process.stdout, self._max_output_bytes))
            stderr_task = asyncio.create_task(_read_bounded(process.stderr, self._max_output_bytes))
            try:
                await asyncio.wait_for(process.wait(), timeout=timeout)
                stdout, stderr = await asyncio.gather(stdout_task, stderr_task)
            except TimeoutError:
                await _terminate(_ActiveProcess(process=process, job=job))
                await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
                raise DomainError(
                    code="tool.command_timed_out",
                    message="Project command timed out",
                    category=ErrorCategory.UNAVAILABLE,
                    retryable=True,
                ) from None
            except _OutputLimitError:
                await _terminate(_ActiveProcess(process=process, job=job))
                await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
                raise DomainError(
                    code="tool.output_limit_exceeded",
                    message="Project command output exceeded the limit",
                    category=ErrorCategory.UNAVAILABLE,
                ) from None
            except asyncio.CancelledError:
                await _terminate(_ActiveProcess(process=process, job=job))
                await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
                raise
        finally:
            await self._registry.unregister(call_id)
            if job is not None:
                try:
                    job.close()
                except OSError:
                    pass
        return (
            ProcessToolResult(
                exit_code=process.returncode or 0,
                stdout_hash=hashlib.sha256(stdout).hexdigest(),
                stderr_hash=hashlib.sha256(stderr).hexdigest(),
                stdout_bytes=len(stdout),
                stderr_bytes=len(stderr),
            ),
            stdout,
            stderr,
        )

    @staticmethod
    def command_for(
        manifest: ProjectManifest, tool_name: str, command_index: int
    ) -> ProjectCommand:
        return _select_command(manifest, tool_name, command_index)


class _OutputLimitError(Exception):
    pass


async def _read_bounded(
    stream: asyncio.StreamReader | None,
    max_bytes: int,
) -> bytes:
    if stream is None:
        return b""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await stream.read(65_536)
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > max_bytes:
            raise _OutputLimitError
        chunks.append(chunk)


def _select_command(
    manifest: ProjectManifest,
    tool_name: str,
    command_index: int,
) -> ProjectCommand:
    command_sets: dict[str, tuple[ProjectCommand, ...]] = {
        "shell.build": manifest.build_commands,
        "shell.test": manifest.test_commands,
        "shell.typecheck": manifest.typecheck_commands,
    }
    all_commands = tuple(
        dict.fromkeys(
            (*manifest.build_commands, *manifest.test_commands, *manifest.typecheck_commands)
        )
    )
    commands = command_sets.get(tool_name, all_commands)
    if command_index < 0 or command_index >= len(commands):
        raise _invalid("tool.command_not_registered", "Project command is not registered")
    return commands[command_index]


async def _spawn(
    argv: tuple[str, ...],
    cwd: Path,
) -> tuple[asyncio.subprocess.Process, WindowsJob | None]:
    executable_name = Path(argv[0]).name.casefold()
    process_argv = (
        (sys.executable, *argv[1:]) if executable_name in {"python", "python.exe"} else argv
    )
    environment = _safe_environment()
    if os.name == "nt":
        from agent_platform.infrastructure.workers.windows_spawn import (
            create_windows_job_subprocess_exec,
        )

        job = WindowsJob.create()
        try:
            process = await create_windows_job_subprocess_exec(
                job,
                *process_argv,
                cwd=str(cwd),
                env=environment,
            )
        except BaseException:
            job.close()
            raise
        return process, job
    process = await asyncio.create_subprocess_exec(
        *process_argv,
        cwd=cwd,
        env=environment,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    return process, None


async def _terminate(active: _ActiveProcess) -> None:
    process = active.process
    if process.returncode is not None:
        return
    if active.job is not None:
        try:
            active.job.close()
        except OSError:
            pass
    elif os.name != "nt":
        try:
            _kill_process_group(process.pid, "SIGTERM")
        except (ProcessLookupError, PermissionError):
            pass
    else:
        process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=1.0)
    except TimeoutError:
        if os.name != "nt":
            try:
                _kill_process_group(process.pid, "SIGKILL")
            except (ProcessLookupError, PermissionError):
                pass
        else:
            process.kill()
        try:
            await asyncio.wait_for(process.wait(), timeout=1.0)
        except TimeoutError:
            pass


def _safe_environment() -> dict[str, str]:
    allowed = {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "COMSPEC",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "HOME",
        "LOCALAPPDATA",
        "APPDATA",
        "VIRTUAL_ENV",
    }
    environment = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    interpreter_directory = str(Path(sys.executable).parent)
    current_path = environment.get("PATH", "")
    environment["PATH"] = (
        f"{interpreter_directory}{os.pathsep}{current_path}"
        if current_path
        else interpreter_directory
    )
    return environment


def _kill_process_group(pid: int, signal_name: str) -> None:
    killpg = getattr(os, "killpg", None)
    signal_value = getattr(signal, signal_name, None)
    if not callable(killpg) or signal_value is None:
        raise OSError("POSIX process group controls are unavailable")
    cast(Callable[[int, int], None], killpg)(pid, int(signal_value))


def _invalid(code: str, message: str) -> DomainError:
    return DomainError(code=code, message=message, category=ErrorCategory.INVALID_INPUT)
