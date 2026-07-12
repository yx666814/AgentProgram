import ctypes
import os
import subprocess
from collections.abc import Mapping
from ctypes import wintypes
from functools import cache
from typing import Any, cast

from .windows_job import _load_kernel32

_CREATE_UNICODE_ENVIRONMENT = 0x00000400
_ERROR_INSUFFICIENT_BUFFER = 122
_EXTENDED_STARTUPINFO_PRESENT = 0x00080000
_PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 0x00020002
_PROC_THREAD_ATTRIBUTE_JOB_LIST = 0x0002000D
_STARTF_USESTDHANDLES = 0x00000100


class _StartupInfoW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(wintypes.BYTE)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class _StartupInfoExW(ctypes.Structure):
    _fields_ = [
        ("StartupInfo", _StartupInfoW),
        ("lpAttributeList", ctypes.c_void_p),
    ]


class _ProcessInformation(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


class CreatedWindowsProcess:
    def __init__(self, process_handle: int, thread_handle: int, pid: int) -> None:
        self._process_handle: int | None = process_handle
        self._thread_handle: int | None = thread_handle
        self.pid = pid

    @property
    def process_handle(self) -> int:
        process_handle = self._process_handle
        if process_handle is None:
            raise OSError("Windows process handle ownership was transferred")
        return process_handle

    def disown_process_handle(self) -> None:
        if self._process_handle is None:
            raise OSError("Windows process handle ownership was transferred")
        self._process_handle = None

    def close(self) -> None:
        first_error: OSError | None = None
        for attribute in ("_thread_handle", "_process_handle"):
            handle = cast(int | None, getattr(self, attribute))
            if handle is None:
                continue
            try:
                if not _load_process_kernel32().CloseHandle(handle):
                    raise _windows_error(ctypes.get_last_error())
                setattr(self, attribute, None)
            except OSError as error:
                if first_error is None:
                    first_error = error
        if first_error is not None:
            raise first_error


@cache
def _load_process_kernel32() -> Any:
    kernel32 = _load_kernel32()
    kernel32.InitializeProcThreadAttributeList.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    kernel32.InitializeProcThreadAttributeList.restype = wintypes.BOOL
    kernel32.UpdateProcThreadAttribute.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_size_t,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    kernel32.UpdateProcThreadAttribute.restype = wintypes.BOOL
    kernel32.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
    kernel32.DeleteProcThreadAttributeList.restype = None
    kernel32.CreateProcessW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.BOOL,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        ctypes.POINTER(_ProcessInformation),
    ]
    kernel32.CreateProcessW.restype = wintypes.BOOL
    return kernel32


def _windows_error(error_code: int) -> OSError:
    return ctypes.WinError(error_code)


class _ProcThreadAttributeList:
    def __init__(self, job_handle: int, inherited_handles: tuple[int, ...]) -> None:
        if not inherited_handles:
            raise OSError("Windows worker stdio handles are unavailable")
        self._kernel32 = _load_process_kernel32()
        self._buffer: Any | None = None
        self._pointer: int | None = None
        self._job_handles = (wintypes.HANDLE * 1)(job_handle)
        self._inherited_handles = (wintypes.HANDLE * len(inherited_handles))(*inherited_handles)

        size = ctypes.c_size_t()
        ctypes.set_last_error(0)
        initialized = self._kernel32.InitializeProcThreadAttributeList(
            None,
            2,
            0,
            ctypes.byref(size),
        )
        size_error = ctypes.get_last_error()
        if initialized or size.value == 0 or size_error != _ERROR_INSUFFICIENT_BUFFER:
            raise _windows_error(size_error)

        self._buffer = ctypes.create_string_buffer(size.value)
        pointer = ctypes.cast(self._buffer, ctypes.c_void_p)
        if not self._kernel32.InitializeProcThreadAttributeList(
            pointer,
            2,
            0,
            ctypes.byref(size),
        ):
            raise _windows_error(ctypes.get_last_error())
        self._pointer = cast(int, pointer.value)
        try:
            self._update(
                _PROC_THREAD_ATTRIBUTE_JOB_LIST,
                self._job_handles,
                ctypes.sizeof(self._job_handles),
            )
            self._update(
                _PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
                self._inherited_handles,
                ctypes.sizeof(self._inherited_handles),
            )
        except BaseException:
            self.close()
            raise

    @property
    def pointer(self) -> int:
        pointer = self._pointer
        if pointer is None:
            raise OSError("Windows process attribute list is closed")
        return pointer

    def _update(self, attribute: int, values: Any, size: int) -> None:
        if not self._kernel32.UpdateProcThreadAttribute(
            self.pointer,
            0,
            attribute,
            ctypes.cast(values, ctypes.c_void_p),
            size,
            None,
            None,
        ):
            raise _windows_error(ctypes.get_last_error())

    def close(self) -> None:
        pointer = self._pointer
        if pointer is None:
            return
        self._kernel32.DeleteProcThreadAttributeList(pointer)
        self._pointer = None


def _build_environment_buffer(env: Mapping[str, str] | None) -> Any | None:
    if env is None:
        return None
    entries: list[str] = []
    for key, value in env.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise TypeError("Windows worker environment must contain text")
        if not key or "=" in key[1:] or "\0" in key or "\0" in value:
            raise ValueError("Windows worker environment is invalid")
        entries.append(f"{key}={value}")
    entries.sort(key=str.upper)
    return ctypes.create_unicode_buffer("\0".join(entries) + "\0")


def _build_command_line(args: Any) -> str:
    if isinstance(args, str):
        command_line = args
    elif isinstance(args, bytes):
        raise TypeError("Windows worker arguments must contain text")
    elif isinstance(args, os.PathLike):
        command_line = os.fsdecode(args)
    else:
        command_line = subprocess.list2cmdline(args)
    if "\0" in command_line:
        raise ValueError("Windows worker command line is invalid")
    return command_line


def create_process_in_job(
    *,
    job_handle: int,
    args: Any,
    executable: Any,
    cwd: Any,
    env: Mapping[str, str] | None,
    creationflags: int,
    stdin_handle: int,
    stdout_handle: int,
    stderr_handle: int,
) -> CreatedWindowsProcess:
    command_line = _build_command_line(args)
    application_name = None if executable is None else os.fsdecode(executable)
    current_directory = None if cwd is None else os.fsdecode(cwd)
    environment_buffer = _build_environment_buffer(env)
    process_information = _ProcessInformation()
    startup_info = _StartupInfoExW()
    startup_info.StartupInfo.cb = ctypes.sizeof(startup_info)
    startup_info.StartupInfo.dwFlags = _STARTF_USESTDHANDLES
    startup_info.StartupInfo.hStdInput = stdin_handle
    startup_info.StartupInfo.hStdOutput = stdout_handle
    startup_info.StartupInfo.hStdError = stderr_handle
    inherited_handles = tuple({stdin_handle, stdout_handle, stderr_handle})
    attributes = _ProcThreadAttributeList(job_handle, inherited_handles)
    startup_info.lpAttributeList = attributes.pointer
    command_line_buffer = ctypes.create_unicode_buffer(command_line)
    process_flags = creationflags | _EXTENDED_STARTUPINFO_PRESENT
    if environment_buffer is not None:
        process_flags |= _CREATE_UNICODE_ENVIRONMENT
    try:
        created = _load_process_kernel32().CreateProcessW(
            application_name,
            command_line_buffer,
            None,
            None,
            True,
            process_flags,
            environment_buffer,
            current_directory,
            ctypes.byref(startup_info),
            ctypes.byref(process_information),
        )
        create_error = 0 if created else ctypes.get_last_error()
    finally:
        attributes.close()
    if not created:
        raise _windows_error(create_error)
    return CreatedWindowsProcess(
        process_handle=int(process_information.hProcess),
        thread_handle=int(process_information.hThread),
        pid=int(process_information.dwProcessId),
    )
