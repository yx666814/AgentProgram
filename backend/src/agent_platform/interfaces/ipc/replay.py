from __future__ import annotations

import argparse
import hashlib
import re
from collections import deque
from dataclasses import dataclass, field
from typing import Final

MIN_REPLAY_WINDOW_CAPACITY: Final[int] = 64
DEFAULT_REPLAY_WINDOW_CAPACITY: Final[int] = 4096
MAX_REPLAY_WINDOW_CAPACITY: Final[int] = 65_536
MAX_IPC_MESSAGE_ID_LENGTH: Final[int] = 128

_CANONICAL_DECIMAL = re.compile(r"[1-9][0-9]*\Z")


class IpcReplayError(ValueError):
    """Raised when an IPC message violates replay-window rules."""


def validate_replay_window_capacity(value: object) -> int:
    if type(value) is not int:
        raise ValueError("replay-window capacity must be an integer")
    if not MIN_REPLAY_WINDOW_CAPACITY <= value <= MAX_REPLAY_WINDOW_CAPACITY:
        raise ValueError("replay-window capacity is outside the supported range")
    return value


def parse_replay_window_capacity_arg(value: str) -> int:
    if _CANONICAL_DECIMAL.fullmatch(value) is None:
        raise argparse.ArgumentTypeError("must be a supported replay-window capacity")
    try:
        return validate_replay_window_capacity(int(value, 10))
    except ValueError:
        raise argparse.ArgumentTypeError("must be a supported replay-window capacity") from None


@dataclass(slots=True)
class ReplayWindow:
    capacity: int = DEFAULT_REPLAY_WINDOW_CAPACITY
    _last_sequence: int = field(default=0, init=False, repr=False)
    _message_digests: deque[bytes] = field(default_factory=deque, init=False, repr=False)
    _message_digest_set: set[bytes] = field(default_factory=set, init=False, repr=False)

    def __post_init__(self) -> None:
        self.capacity = validate_replay_window_capacity(self.capacity)

    @property
    def last_sequence(self) -> int:
        return self._last_sequence

    @property
    def remembered_message_count(self) -> int:
        return len(self._message_digests)

    def accept(self, *, sequence: int, message_id: str) -> None:
        if type(sequence) is not int or sequence <= 0:
            raise IpcReplayError("IPC sequence is invalid")
        if sequence != self._last_sequence + 1:
            raise IpcReplayError("IPC sequence is not consecutive")
        if (
            type(message_id) is not str
            or not message_id
            or len(message_id) > MAX_IPC_MESSAGE_ID_LENGTH
        ):
            raise IpcReplayError("IPC message ID is invalid")
        digest = hashlib.sha256(message_id.encode("utf-8")).digest()
        if digest in self._message_digest_set:
            raise IpcReplayError("IPC message ID was recently reused")
        self._message_digests.append(digest)
        self._message_digest_set.add(digest)
        if len(self._message_digests) > self.capacity:
            self._message_digest_set.remove(self._message_digests.popleft())
        self._last_sequence = sequence
