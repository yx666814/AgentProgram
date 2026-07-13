import asyncio
import inspect
import subprocess
import sys
import textwrap
from typing import get_type_hints

from agent_platform.infrastructure.workers.windows_job import WindowsJob
from agent_platform.infrastructure.workers.windows_spawn import (
    create_windows_job_subprocess_exec,
)


def test_windows_spawn_public_metadata_is_runtime_resolvable() -> None:
    hints = get_type_hints(create_windows_job_subprocess_exec)

    assert hints["job"] is WindowsJob
    assert hints["args"] is str
    assert hints["return"] is asyncio.subprocess.Process
    assert inspect.getdoc(create_windows_job_subprocess_exec) == (
        "Spawn a piped process atomically inside a Windows Job Object."
    )


def test_windows_spawn_import_is_safe_when_windows_asyncio_modules_are_unavailable() -> None:
    script = textwrap.dedent(
        """
        import asyncio
        import builtins
        import os
        import types

        real_import = builtins.__import__
        fake_os = types.ModuleType("os")
        fake_os.name = "posix"

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if (
                name == "os"
                and globals is not None
                and globals.get("__name__")
                == "agent_platform.infrastructure.workers.windows_spawn"
            ):
                return fake_os
            windows_fromlist = name == "asyncio" and any(
                item in {"windows_events", "windows_utils"} for item in (fromlist or ())
            )
            if name in {"asyncio.windows_events", "asyncio.windows_utils"} or windows_fromlist:
                raise ImportError("simulated POSIX asyncio")
            return real_import(name, globals, locals, fromlist, level)

        builtins.__import__ = guarded_import

        from agent_platform.infrastructure.workers.windows_spawn import (
            create_windows_job_subprocess_exec,
        )

        coroutine = create_windows_job_subprocess_exec(object(), "ignored")
        try:
            coroutine.send(None)
        except OSError as error:
            assert str(error) == "atomic Windows worker spawn is unavailable"
        else:
            raise AssertionError("POSIX factory call did not fail closed")

        print("import-safe")
        """
    )

    completed = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines() == ["import-safe"]
