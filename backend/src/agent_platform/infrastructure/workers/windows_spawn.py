"""CPython 3.12 Proactor bridge for atomic Windows Job process creation."""

import asyncio
import os
import subprocess
import sys
from asyncio import windows_events, windows_utils
from collections.abc import Mapping
from typing import Any, cast

from agent_platform.infrastructure.async_cleanup import await_cancellation_resistant

from .windows_create_process import create_process_in_job
from .windows_job import WindowsJob

_STREAM_LIMIT = 2**16


class _AtomicJobPopen(windows_utils.Popen[bytes]):
    def __init__(self, args: Any, *, job_handle: int, **kwargs: Any) -> None:
        self._atomic_job_handle = job_handle
        super().__init__(args, **kwargs)

    def _execute_child(
        self,
        args: Any,
        executable: Any,
        preexec_fn: Any,
        close_fds: bool,
        pass_fds: tuple[int, ...],
        cwd: Any,
        env: Mapping[str, str] | None,
        startupinfo: Any,
        creationflags: int,
        shell: bool,
        p2cread: Any,
        p2cwrite: Any,
        c2pread: Any,
        c2pwrite: Any,
        errread: Any,
        errwrite: Any,
        unused_restore_signals: bool,
        unused_gid: Any,
        unused_gids: Any,
        unused_uid: Any,
        unused_umask: Any,
        unused_start_new_session: bool,
        unused_process_group: int,
    ) -> None:
        del (
            close_fds,
            unused_restore_signals,
            unused_gid,
            unused_gids,
            unused_uid,
            unused_umask,
            unused_start_new_session,
            unused_process_group,
        )
        try:
            if preexec_fn is not None or pass_fds or startupinfo is not None or shell:
                raise ValueError("unsupported Windows worker spawn option")
            sys.audit("subprocess.Popen", executable, args, cwd, env)
            created = create_process_in_job(
                job_handle=self._atomic_job_handle,
                args=args,
                executable=executable,
                cwd=cwd,
                env=env,
                creationflags=creationflags,
                stdin_handle=int(p2cread),
                stdout_handle=int(c2pwrite),
                stderr_handle=int(errwrite),
            )
            try:
                process_handle = subprocess.Handle(  # type: ignore[attr-defined]
                    created.process_handle
                )
                created.disown_process_handle()
                self._handle = process_handle
                self._child_created = True
                self.pid = created.pid
            finally:
                created.close()
        finally:
            cast(Any, self)._close_pipe_fds(
                p2cread,
                p2cwrite,
                c2pread,
                c2pwrite,
                errread,
                errwrite,
            )

    def close_parent_resources(self) -> None:
        for name in ("stdin", "stdout", "stderr"):
            pipe = getattr(self, name, None)
            if pipe is not None:
                pipe.close()
        self.close_process_handle()

    def close_process_handle(self) -> None:
        handle = getattr(self, "_handle", None)
        if handle is not None:
            handle.Close()


_WindowsSubprocessTransportBase: Any = windows_events._WindowsSubprocessTransport  # type: ignore[attr-defined]


class _AtomicJobSubprocessTransport(_WindowsSubprocessTransportBase):  # type: ignore[misc]
    _atomic_connect_task: asyncio.Task[None] | None
    _atomic_proc: _AtomicJobPopen
    _atomic_process_exited: asyncio.Event

    def _start(
        self,
        args: Any,
        shell: bool,
        stdin: Any,
        stdout: Any,
        stderr: Any,
        bufsize: int,
        **kwargs: Any,
    ) -> None:
        job_handle = cast(int, kwargs.pop("job_handle"))
        self._atomic_connect_task = None
        self._atomic_process_exited = asyncio.Event()
        self._atomic_proc = _AtomicJobPopen(
            args,
            job_handle=job_handle,
            shell=shell,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            bufsize=bufsize,
            **kwargs,
        )
        self._proc = self._atomic_proc

        def process_exited(completion: asyncio.Future[Any]) -> None:
            del completion
            try:
                returncode = self._atomic_proc.poll()
                self._atomic_proc.close_process_handle()
                self._process_exited(returncode)
            finally:
                self._atomic_process_exited.set()

        completion = self._loop._proactor.wait_for_handle(int(self._atomic_proc._handle))
        completion.add_done_callback(process_exited)

    async def _connect_pipes(self, waiter: asyncio.Future[None] | None) -> None:
        connect_task = asyncio.current_task()
        if connect_task is None:
            raise RuntimeError("Windows pipe connection task is unavailable")
        self._atomic_connect_task = connect_task
        await super()._connect_pipes(waiter)

    def close_spawn_resources(self) -> None:
        self._atomic_proc.close_parent_resources()

    async def cleanup_failed_spawn(self) -> None:
        connect_task = self._atomic_connect_task
        if connect_task is not None and not connect_task.done():
            connect_task.cancel()
        if connect_task is not None and connect_task is not asyncio.current_task():
            await asyncio.gather(connect_task, return_exceptions=True)
        await self._atomic_process_exited.wait()
        self.close_spawn_resources()


async def create_windows_job_subprocess_exec(
    job: WindowsJob,
    *args: str,
) -> asyncio.subprocess.Process:
    """Spawn a piped process atomically inside ``job`` and expose asyncio semantics."""

    if os.name != "nt":
        raise OSError("atomic Windows worker spawn is unavailable")
    loop = asyncio.get_running_loop()
    if getattr(loop, "_proactor", None) is None:
        raise OSError("atomic Windows worker spawn requires a proactor event loop")
    protocol = asyncio.subprocess.SubprocessStreamProtocol(limit=_STREAM_LIMIT, loop=loop)
    waiter: asyncio.Future[None] = loop.create_future()
    transport: _AtomicJobSubprocessTransport | None = None
    try:
        duplicated_job_handle = job._duplicate_handle()
        try:
            transport = _AtomicJobSubprocessTransport(
                loop,
                protocol,
                args,
                False,
                asyncio.subprocess.PIPE,
                asyncio.subprocess.PIPE,
                asyncio.subprocess.PIPE,
                0,
                waiter=waiter,
                job_handle=duplicated_job_handle.value,
            )
        finally:
            duplicated_job_handle.close()
        await waiter
    except BaseException:
        try:
            job.close()
        except OSError:
            pass
        if transport is not None:
            transport.close()
            try:
                await await_cancellation_resistant(transport.cleanup_failed_spawn())
            except BaseException:
                transport.close_spawn_resources()
        raise
    return asyncio.subprocess.Process(transport, protocol, loop)
