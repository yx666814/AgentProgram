from __future__ import annotations

import threading
from collections.abc import Callable


class ShutdownCoordinator:
    def __init__(self) -> None:
        self._callback: Callable[[], None] | None = None
        self._requested = False
        self._lock = threading.Lock()

    @property
    def requested(self) -> bool:
        with self._lock:
            return self._requested

    def bind(self, callback: Callable[[], None]) -> None:
        with self._lock:
            if self._callback is not None:
                raise RuntimeError("shutdown callback is already bound")
            self._callback = callback

    def request(self) -> bool:
        callback: Callable[[], None] | None
        with self._lock:
            if self._requested:
                return False
            self._requested = True
            callback = self._callback
        if callback is not None:
            callback()
        return True
