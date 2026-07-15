import argparse

import pytest

from agent_platform.interfaces.ipc.replay import (
    DEFAULT_REPLAY_WINDOW_CAPACITY,
    MAX_IPC_MESSAGE_ID_LENGTH,
    MAX_REPLAY_WINDOW_CAPACITY,
    MIN_REPLAY_WINDOW_CAPACITY,
    IpcReplayError,
    ReplayWindow,
    parse_replay_window_capacity_arg,
    validate_replay_window_capacity,
)


@pytest.mark.parametrize(
    "capacity",
    [MIN_REPLAY_WINDOW_CAPACITY, DEFAULT_REPLAY_WINDOW_CAPACITY, MAX_REPLAY_WINDOW_CAPACITY],
)
def test_replay_window_accepts_supported_capacities(capacity: int) -> None:
    assert ReplayWindow(capacity).capacity == capacity


@pytest.mark.parametrize(
    "capacity",
    [True, 64.0, "64", MIN_REPLAY_WINDOW_CAPACITY - 1, MAX_REPLAY_WINDOW_CAPACITY + 1],
)
def test_capacity_validator_rejects_invalid_values(capacity: object) -> None:
    with pytest.raises(ValueError):
        validate_replay_window_capacity(capacity)


@pytest.mark.parametrize("value", ["64", "4096", "65536"])
def test_cli_capacity_parser_accepts_canonical_decimal(value: str) -> None:
    assert parse_replay_window_capacity_arg(value) == int(value)


@pytest.mark.parametrize("value", [" 64", "+64", "064", "64 ", "1.5", "65537"])
def test_cli_capacity_parser_rejects_noncanonical_or_out_of_range(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError) as raised:
        parse_replay_window_capacity_arg(value)
    assert value not in str(raised.value)


def test_replay_window_requires_consecutive_sequence_and_unique_recent_id() -> None:
    window = ReplayWindow(MIN_REPLAY_WINDOW_CAPACITY)
    window.accept(sequence=1, message_id="message-1")

    with pytest.raises(IpcReplayError, match="consecutive"):
        window.accept(sequence=3, message_id="message-3")
    with pytest.raises(IpcReplayError, match="reused"):
        window.accept(sequence=2, message_id="message-1")

    assert window.last_sequence == 1
    assert window.remembered_message_count == 1


@pytest.mark.parametrize("sequence", [0, -1, True, 1.0, "1"])
def test_replay_window_rejects_invalid_sequence(sequence: object) -> None:
    with pytest.raises(IpcReplayError, match="sequence"):
        ReplayWindow().accept(sequence=sequence, message_id="message")  # type: ignore[arg-type]


@pytest.mark.parametrize("message_id", ["", "x" * (MAX_IPC_MESSAGE_ID_LENGTH + 1)])
def test_replay_window_rejects_invalid_message_id(message_id: str) -> None:
    with pytest.raises(IpcReplayError, match="message ID"):
        ReplayWindow().accept(sequence=1, message_id=message_id)


def test_replay_window_evicts_digests_at_capacity() -> None:
    window = ReplayWindow(MIN_REPLAY_WINDOW_CAPACITY)
    for sequence in range(1, MIN_REPLAY_WINDOW_CAPACITY * 3 + 1):
        window.accept(sequence=sequence, message_id=f"message-{sequence}")

    assert window.last_sequence == MIN_REPLAY_WINDOW_CAPACITY * 3
    assert window.remembered_message_count == MIN_REPLAY_WINDOW_CAPACITY
    assert all(len(digest) == 32 for digest in window._message_digests)
    assert not any(b"message" in digest for digest in window._message_digests)

    window.accept(
        sequence=MIN_REPLAY_WINDOW_CAPACITY * 3 + 1,
        message_id="message-1",
    )
