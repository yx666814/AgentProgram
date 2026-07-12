import ctypes
import os
import threading
from typing import Any, Self

_PROCESS_TERMINATE = 0x0001
_PROCESS_SET_QUOTA = 0x0100
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000


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
        self._close_lock = threading.Lock()

    @classmethod
    def create_for_process(cls, pid: int) -> Self:
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

            process_handle = kernel32.OpenProcess(
                _PROCESS_TERMINATE | _PROCESS_SET_QUOTA,
                False,
                pid,
            )
            if not process_handle:
                raise _last_windows_error()
            process_handle = int(process_handle)
            try:
                if not kernel32.AssignProcessToJobObject(job_handle, process_handle):
                    raise _last_windows_error()
            finally:
                _close_raw_handle(kernel32, process_handle)
            return cls(kernel32, job_handle)
        except BaseException:
            _close_raw_handle(kernel32, job_handle)
            raise

    def close(self) -> None:
        with self._close_lock:
            handle = self._handle
            if handle is None:
                return
            _close_raw_handle(self._kernel32, handle)
            self._handle = None
