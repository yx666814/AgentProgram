import ctypes
import os
import re
import threading
from functools import cache
from typing import Any, Self
from uuid import uuid4

_ERROR_ALREADY_EXISTS = 183
_EVENT_MODIFY_STATE = 0x0002
_INFINITE = 0xFFFFFFFF
_PROCESS_TERMINATE = 0x0001
_PROCESS_SET_QUOTA = 0x0100
_SYNCHRONIZE = 0x00100000
_WAIT_OBJECT_0 = 0
_WAIT_TIMEOUT = 258
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_START_GATE_NAME_PATTERN = re.compile(r"Local\\AgentPlatformWorkerStart_[0-9a-f]{32}")
_WINDOWS_HANDLE_LOCK = threading.Lock()


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("read_operation_count", ctypes.c_ulonglong),
        ("write_operation_count", ctypes.c_ulonglong),
        ("other_operation_count", ctypes.c_ulonglong),
        ("read_transfer_count", ctypes.c_ulonglong),
        ("write_transfer_count", ctypes.c_ulonglong),
        ("other_transfer_count", ctypes.c_ulonglong),
    ]


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("per_process_user_time_limit", ctypes.c_longlong),
        ("per_job_user_time_limit", ctypes.c_longlong),
        ("limit_flags", ctypes.c_ulong),
        ("minimum_working_set_size", ctypes.c_size_t),
        ("maximum_working_set_size", ctypes.c_size_t),
        ("active_process_limit", ctypes.c_ulong),
        ("affinity", ctypes.c_size_t),
        ("priority_class", ctypes.c_ulong),
        ("scheduling_class", ctypes.c_ulong),
    ]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("basic_limit_information", _BasicLimitInformation),
        ("io_info", _IoCounters),
        ("process_memory_limit", ctypes.c_size_t),
        ("job_memory_limit", ctypes.c_size_t),
        ("peak_process_memory_used", ctypes.c_size_t),
        ("peak_job_memory_used", ctypes.c_size_t),
    ]


@cache
def _load_kernel32() -> Any:
    if os.name != "nt":
        raise OSError("Windows Job Objects are unavailable")
    win_dll = getattr(ctypes, "WinDLL", None)
    if win_dll is None:
        raise OSError("Windows Job Objects are unavailable")
    kernel32 = win_dll("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    kernel32.CreateJobObjectW.restype = ctypes.c_void_p
    kernel32.SetInformationJobObject.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_ulong,
    ]
    kernel32.SetInformationJobObject.restype = ctypes.c_int
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel32.AssignProcessToJobObject.restype = ctypes.c_int
    kernel32.CreateEventW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_wchar_p,
    ]
    kernel32.CreateEventW.restype = ctypes.c_void_p
    kernel32.OpenEventW.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_wchar_p]
    kernel32.OpenEventW.restype = ctypes.c_void_p
    kernel32.SetEvent.argtypes = [ctypes.c_void_p]
    kernel32.SetEvent.restype = ctypes.c_int
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel32.WaitForSingleObject.restype = ctypes.c_ulong
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    return kernel32


def _last_windows_error() -> OSError:
    return ctypes.WinError(ctypes.get_last_error())


def _close_raw_handle(kernel32: Any, handle: int) -> None:
    if not kernel32.CloseHandle(handle):
        raise _last_windows_error()


class WindowsJob:
    """Own one kill-on-close Windows Job Object handle."""

    def __init__(self, kernel32: Any, handle: int) -> None:
        self._kernel32 = kernel32
        self._handle: int | None = handle

    @classmethod
    def create(cls) -> Self:
        kernel32 = _load_kernel32()
        job_handle = kernel32.CreateJobObjectW(None, None)
        if not job_handle:
            raise _last_windows_error()
        job_handle = int(job_handle)
        try:
            limits = _ExtendedLimitInformation()
            limits.basic_limit_information.limit_flags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not kernel32.SetInformationJobObject(
                job_handle,
                _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                ctypes.byref(limits),
                ctypes.sizeof(limits),
            ):
                raise _last_windows_error()
            return cls(kernel32, job_handle)
        except BaseException:
            _close_raw_handle(kernel32, job_handle)
            raise

    @classmethod
    def create_for_process(cls, pid: int) -> Self:
        job = cls.create()
        try:
            job.assign_process(pid)
            return job
        except BaseException:
            job.close()
            raise

    def assign_process(self, pid: int) -> None:
        with _WINDOWS_HANDLE_LOCK:
            job_handle = self._handle
            if job_handle is None:
                raise OSError("Windows Job Object is closed")
            process_handle = self._kernel32.OpenProcess(
                _PROCESS_TERMINATE | _PROCESS_SET_QUOTA,
                False,
                pid,
            )
            if not process_handle:
                raise _last_windows_error()
            process_handle = int(process_handle)
            try:
                if not self._kernel32.AssignProcessToJobObject(job_handle, process_handle):
                    raise _last_windows_error()
            finally:
                _close_raw_handle(self._kernel32, process_handle)

    def close(self) -> None:
        with _WINDOWS_HANDLE_LOCK:
            handle = self._handle
            if handle is None:
                return
            _close_raw_handle(self._kernel32, handle)
            self._handle = None


class WindowsStartGate:
    """Own paired named Events for worker-ready and worker-release synchronization."""

    def __init__(self, kernel32: Any, handle: int, ready_handle: int, name: str) -> None:
        self._kernel32 = kernel32
        self._handle: int | None = handle
        self._ready_handle: int | None = ready_handle
        self._name = name

    @classmethod
    def create(cls) -> Self:
        kernel32 = _load_kernel32()
        for _ in range(3):
            name = f"Local\\AgentPlatformWorkerStart_{uuid4().hex}"
            ctypes.set_last_error(0)
            event_handle = kernel32.CreateEventW(None, True, False, name)
            if not event_handle:
                raise _last_windows_error()
            event_handle = int(event_handle)
            if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
                _close_raw_handle(kernel32, event_handle)
                continue
            try:
                ctypes.set_last_error(0)
                ready_handle = kernel32.CreateEventW(None, True, False, f"{name}_Ready")
                if not ready_handle:
                    raise _last_windows_error()
                ready_handle = int(ready_handle)
                if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
                    _close_raw_handle(kernel32, ready_handle)
                    _close_raw_handle(kernel32, event_handle)
                    continue
                return cls(kernel32, event_handle, ready_handle, name)
            except BaseException:
                _close_raw_handle(kernel32, event_handle)
                raise
        raise OSError("could not create a unique Windows start gate")

    @property
    def name(self) -> str:
        return self._name

    def release(self) -> None:
        with _WINDOWS_HANDLE_LOCK:
            handle = self._handle
            if handle is None:
                raise OSError("Windows start gate is closed")
            if not self._kernel32.SetEvent(handle):
                raise _last_windows_error()

    def wait_until_opened(self, timeout_seconds: float) -> None:
        timeout_milliseconds = max(0, min(int(timeout_seconds * 1000), _INFINITE - 1))
        with _WINDOWS_HANDLE_LOCK:
            ready_handle = self._ready_handle
            if ready_handle is None:
                raise OSError("Windows start gate is closed")
            wait_result = self._kernel32.WaitForSingleObject(
                ready_handle,
                timeout_milliseconds,
            )
            if wait_result == _WAIT_TIMEOUT:
                raise TimeoutError("Windows start gate was not opened")
            if wait_result != _WAIT_OBJECT_0:
                raise _last_windows_error()

    def close(self) -> None:
        with _WINDOWS_HANDLE_LOCK:
            handle = self._handle
            ready_handle = self._ready_handle
            error: OSError | None = None
            if handle is not None:
                try:
                    _close_raw_handle(self._kernel32, handle)
                    self._handle = None
                except OSError as caught:
                    error = caught
            if ready_handle is not None:
                try:
                    _close_raw_handle(self._kernel32, ready_handle)
                    self._ready_handle = None
                except OSError as caught:
                    if error is None:
                        error = caught
            if error is not None:
                raise error


def wait_for_windows_start_gate(name: str) -> None:
    """Open and wait for a supervisor-owned start gate without exposing its value."""

    if _START_GATE_NAME_PATTERN.fullmatch(name) is None:
        raise OSError("invalid Windows start gate name")
    kernel32 = _load_kernel32()
    event_handle = kernel32.OpenEventW(_SYNCHRONIZE, False, name)
    if not event_handle:
        raise _last_windows_error()
    event_handle = int(event_handle)
    ready_handle: int | None = None
    try:
        opened_ready_handle = kernel32.OpenEventW(_EVENT_MODIFY_STATE, False, f"{name}_Ready")
        if not opened_ready_handle:
            raise _last_windows_error()
        ready_handle = int(opened_ready_handle)
        if not kernel32.SetEvent(ready_handle):
            raise _last_windows_error()
        wait_result = kernel32.WaitForSingleObject(event_handle, _INFINITE)
        if wait_result != _WAIT_OBJECT_0:
            raise _last_windows_error()
    finally:
        if ready_handle is not None:
            _close_raw_handle(kernel32, ready_handle)
        _close_raw_handle(kernel32, event_handle)
