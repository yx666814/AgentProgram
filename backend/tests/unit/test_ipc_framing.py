import json
from datetime import datetime
from typing import Any, cast

import pytest
from pydantic import ValidationError

from agent_platform.interfaces.ipc.framing import (
    MAX_BODY_BYTES,
    MAX_HEADER_BYTES,
    FrameDecoder,
    FramingError,
    encode_frame,
)
from agent_platform.interfaces.ipc.messages import IpcMessage


class _PayloadMarker:
    def __repr__(self) -> str:
        return "PAYLOAD_VALUE_MARKER"


def test_decoder_handles_partial_unicode_frame() -> None:
    message = IpcMessage(
        message_id="msg_1",
        correlation_id=None,
        sequence=7,
        project_id="project_1",
        task_id="task_1",
        type="event",
        payload={"text": "你好\nworker"},
    )
    encoded = encode_frame(message)
    decoder = FrameDecoder()
    result: list[IpcMessage] = []

    for byte in encoded:
        result.extend(decoder.feed(bytes([byte])))

    assert result == [message]


def test_decoder_reads_two_frames_from_one_chunk() -> None:
    first = IpcMessage(message_id="m1", sequence=1, project_id="p", type="heartbeat")
    second = IpcMessage(message_id="m2", sequence=2, project_id="p", type="ack")

    assert FrameDecoder().feed(encode_frame(first) + encode_frame(second)) == [first, second]


def test_message_rejects_unsupported_protocol_version() -> None:
    with pytest.raises(ValidationError):
        IpcMessage.model_validate(
            {
                "protocol_version": 2,
                "message_id": "m1",
                "sequence": 1,
                "project_id": "p",
                "type": "event",
            }
        )


def test_message_rejects_unsupported_type() -> None:
    with pytest.raises(ValidationError):
        IpcMessage.model_validate(
            {"message_id": "m1", "sequence": 1, "project_id": "p", "type": "unknown"}
        )


def test_message_rejects_negative_sequence() -> None:
    with pytest.raises(ValidationError):
        IpcMessage(message_id="m1", sequence=-1, project_id="p", type="event")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("protocol_version", True),
        ("sequence", True),
        ("sequence", "1"),
        ("sequence", 1.0),
    ],
)
def test_message_rejects_non_strict_wire_scalars_from_python(
    field: str,
    value: object,
) -> None:
    data = {
        "protocol_version": 1,
        "message_id": "m1",
        "sequence": 1,
        "project_id": "p",
        "type": "event",
    }
    data[field] = value

    with pytest.raises(ValidationError):
        IpcMessage.model_validate(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("protocol_version", True),
        ("sequence", True),
        ("sequence", "1"),
        ("sequence", 1.0),
    ],
)
def test_message_rejects_non_strict_wire_scalars_from_json(
    field: str,
    value: object,
) -> None:
    data = {
        "protocol_version": 1,
        "message_id": "m1",
        "sequence": 1,
        "project_id": "p",
        "type": "event",
    }
    data[field] = value

    with pytest.raises(ValidationError):
        IpcMessage.model_validate_json(json.dumps(data))


def test_message_accepts_strict_integer_scalars_and_aware_json_timestamp() -> None:
    message = IpcMessage.model_validate_json(
        json.dumps(
            {
                "protocol_version": 1,
                "message_id": "m1",
                "sequence": 1,
                "project_id": "p",
                "type": "event",
                "timestamp": "2026-07-11T00:00:00Z",
            }
        )
    )

    assert message.protocol_version == 1
    assert message.sequence == 1
    assert message.timestamp.utcoffset() is not None


@pytest.mark.parametrize("field", ["message_id", "project_id"])
def test_message_rejects_empty_required_identifier(field: str) -> None:
    data = {"message_id": "m1", "sequence": 1, "project_id": "p", "type": "event"}
    data[field] = ""

    with pytest.raises(ValidationError):
        IpcMessage.model_validate(data)


@pytest.mark.parametrize("field", ["correlation_id", "task_id"])
def test_message_rejects_empty_optional_identifier(field: str) -> None:
    data = {
        "message_id": "m1",
        "sequence": 1,
        "project_id": "p",
        "type": "event",
        field: "",
    }

    with pytest.raises(ValidationError):
        IpcMessage.model_validate(data)


def test_message_allows_none_for_optional_identifiers() -> None:
    message = IpcMessage(
        message_id="m1",
        correlation_id=None,
        sequence=1,
        project_id="p",
        task_id=None,
        type="event",
    )

    assert message.correlation_id is None
    assert message.task_id is None


def test_message_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError):
        IpcMessage(
            message_id="m1",
            sequence=1,
            project_id="p",
            type="event",
            timestamp=datetime(2026, 7, 11),
        )


def test_message_payload_defaults_are_independent() -> None:
    first = IpcMessage(message_id="m1", sequence=1, project_id="p", type="event")
    second = IpcMessage(message_id="m2", sequence=2, project_id="p", type="event")

    first.payload["changed"] = True

    assert second.payload == {}


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"value": float("nan")}, id="nan"),
        pytest.param({"value": float("inf")}, id="positive-infinity"),
        pytest.param({"value": float("-inf")}, id="negative-infinity"),
        pytest.param({"value": {1, 2}}, id="set"),
        pytest.param({"value": (1, 2)}, id="tuple"),
        pytest.param({"value": b"bytes"}, id="bytes"),
        pytest.param({1: "value"}, id="non-string-root-key"),
        pytest.param({"nested": {1: "value"}}, id="non-string-nested-key"),
        pytest.param({"value": _PayloadMarker()}, id="custom-object"),
        pytest.param({"nested": [{"value": (1, 2)}]}, id="nested-tuple"),
    ],
)
def test_message_rejects_non_json_payload_values(payload: object) -> None:
    with pytest.raises(ValidationError) as error:
        IpcMessage.model_validate(
            {
                "message_id": "m1",
                "sequence": 1,
                "project_id": "p",
                "type": "event",
                "payload": payload,
            }
        )

    assert "PAYLOAD_VALUE_MARKER" not in str(error.value)
    assert "PAYLOAD_VALUE_MARKER" not in repr(error.value)


def test_message_valid_json_payload_round_trips_without_transformation() -> None:
    payload = {
        "none": None,
        "boolean": True,
        "integer": 7,
        "float": 2.5,
        "string": "你好",
        "list": [None, False, 3, 4.5, "value", {"nested": [1, 2]}],
    }
    message = IpcMessage(
        message_id="m1",
        sequence=1,
        project_id="p",
        type="event",
        payload=payload,
    )

    assert FrameDecoder().feed(encode_frame(message)) == [message]
    assert message.payload == payload


@pytest.mark.parametrize("cycle_kind", ["dict", "list"])
def test_message_rejects_cyclic_payload_without_recursion_error(cycle_kind: str) -> None:
    marker = "CYCLE_PAYLOAD_MARKER"
    if cycle_kind == "dict":
        payload: dict[str, Any] = {"marker": marker}
        payload["cycle"] = payload
    else:
        cyclic_list: list[Any] = [marker]
        cyclic_list.append(cyclic_list)
        payload = {"cycle": cyclic_list}

    with pytest.raises(ValidationError) as error:
        IpcMessage.model_validate(
            {
                "message_id": "m1",
                "sequence": 1,
                "project_id": "p",
                "type": "event",
                "payload": payload,
            }
        )

    assert marker not in str(error.value)
    assert marker not in repr(error.value)


def test_encode_rejects_oversized_body() -> None:
    message = IpcMessage(
        message_id="m1",
        sequence=1,
        project_id="p",
        type="event",
        payload={"text": "x" * MAX_BODY_BYTES},
    )

    with pytest.raises(FramingError):
        encode_frame(message)


@pytest.mark.parametrize(
    ("kind", "invalid_value"),
    [
        ("value", float("nan")),
        ("value", float("inf")),
        ("value", float("-inf")),
        ("value", (1, 2)),
        ("value", {1, 2}),
        ("value", b"bytes"),
        ("non-string-key", "value"),
        ("value", _PayloadMarker()),
        ("value", [{"nested": (1, 2)}]),
    ],
)
def test_encode_rejects_payload_invalidated_by_mutation(
    kind: str,
    invalid_value: object,
) -> None:
    marker = b"ENCODE_PAYLOAD_MARKER"
    message = IpcMessage(
        message_id="m1",
        sequence=1,
        project_id="p",
        type="event",
        payload={"secret": marker.decode()},
    )
    if kind == "non-string-key":
        cast_payload = cast(dict[object, object], message.payload)
        cast_payload[1] = invalid_value
    else:
        message.payload["invalid"] = invalid_value

    with pytest.raises(FramingError) as error:
        encode_frame(message)

    pending: list[BaseException] = [error.value]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        rendered = f"{current!s} {current!r} {current.args!r}".encode()
        assert marker not in rendered
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)


@pytest.mark.parametrize("cycle_kind", ["dict", "list"])
def test_encode_rejects_payload_cycle_added_by_mutation(cycle_kind: str) -> None:
    marker = b"ENCODE_CYCLE_MARKER"
    message = IpcMessage(
        message_id="m1",
        sequence=1,
        project_id="p",
        type="event",
        payload={"secret": marker.decode()},
    )
    if cycle_kind == "dict":
        message.payload["cycle"] = message.payload
    else:
        cyclic_list: list[Any] = []
        cyclic_list.append(cyclic_list)
        message.payload["cycle"] = cyclic_list

    with pytest.raises(FramingError) as error:
        encode_frame(message)

    rendered = f"{error.value!s} {error.value!r} {error.value.args!r}".encode()
    assert marker not in rendered
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__ is True


def test_encode_accepts_payload_mutated_to_valid_json_value() -> None:
    message = IpcMessage(
        message_id="m1",
        sequence=1,
        project_id="p",
        type="event",
    )
    message.payload["added"] = [None, True, 7, 2.5, "value", {"nested": [1]}]

    assert FrameDecoder().feed(encode_frame(message)) == [message]


def test_decoder_rejects_oversized_unterminated_header() -> None:
    decoder = FrameDecoder()

    with pytest.raises(FramingError):
        decoder.feed(b"x" * (MAX_HEADER_BYTES + 4))


@pytest.mark.parametrize("suffix", [b"x", b"xy", b"xyz"])
def test_decoder_rejects_oversized_unterminated_header_with_garbage_suffix(
    suffix: bytes,
) -> None:
    decoder = FrameDecoder()

    with pytest.raises(FramingError):
        decoder.feed((b"x" * MAX_HEADER_BYTES) + suffix)


def test_decoder_rejects_non_ascii_header() -> None:
    decoder = FrameDecoder()
    frame = b"Content-Length: 2\r\nProtocol-Version: 1\r\nX-\xff: value\r\n\r\n{}"

    with pytest.raises(FramingError):
        decoder.feed(frame)


def test_decoder_non_ascii_header_error_chain_hides_raw_header() -> None:
    marker = b"SECRET_HEADER_MARKER"
    frame = b"Content-Length: 2\r\nProtocol-Version: 1 " + marker + b"\xff\r\n\r\n{}"

    with pytest.raises(FramingError) as error:
        FrameDecoder().feed(frame)

    pending: list[BaseException] = [error.value]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        rendered = f"{current!s} {current!r} {current.args!r}".encode()
        assert marker not in rendered
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)


def test_decoder_rejects_malformed_header_line() -> None:
    decoder = FrameDecoder()
    frame = b"Content-Length 2\r\nProtocol-Version: 1\r\n\r\n{}"

    with pytest.raises(FramingError):
        decoder.feed(frame)


def test_decoder_rejects_leading_empty_header_line() -> None:
    message = IpcMessage(message_id="m1", sequence=1, project_id="p", type="event")
    body = message.model_dump_json().encode("utf-8")
    frame = f"\r\nContent-Length: {len(body)}\r\nProtocol-Version: 1\r\n\r\n".encode() + body

    with pytest.raises(FramingError):
        FrameDecoder().feed(frame)


@pytest.mark.parametrize("raw_name", [" Content-Length", "Content-Length "])
def test_decoder_rejects_header_name_whitespace(raw_name: str) -> None:
    message = IpcMessage(message_id="m1", sequence=1, project_id="p", type="event")
    body = message.model_dump_json().encode("utf-8")
    frame = f"{raw_name}: {len(body)}\r\nProtocol-Version: 1\r\n\r\n".encode() + body

    with pytest.raises(FramingError):
        FrameDecoder().feed(frame)


def test_decoder_rejects_duplicate_header_case_insensitively() -> None:
    decoder = FrameDecoder()
    frame = b"Content-Length: 2\r\ncontent-length: 2\r\nProtocol-Version: 1\r\n\r\n{}"

    with pytest.raises(FramingError):
        decoder.feed(frame)


@pytest.mark.parametrize("missing", ["content-length", "protocol-version"])
def test_decoder_rejects_missing_required_header(missing: str) -> None:
    body = (
        IpcMessage(message_id="m1", sequence=1, project_id="p", type="event")
        .model_dump_json()
        .encode("utf-8")
    )
    headers = {
        "content-length": f"Content-Length: {len(body)}".encode(),
        "protocol-version": b"Protocol-Version: 1",
    }
    del headers[missing]
    frame = b"\r\n".join(headers.values()) + b"\r\n\r\n" + body

    with pytest.raises(FramingError):
        FrameDecoder().feed(frame)


def test_decoder_rejects_unknown_header() -> None:
    body = (
        IpcMessage(message_id="m1", sequence=1, project_id="p", type="event")
        .model_dump_json()
        .encode("utf-8")
    )
    frame = (
        f"Content-Length: {len(body)}\r\nProtocol-Version: 1\r\nX-Extra: no\r\n\r\n".encode() + body
    )

    with pytest.raises(FramingError):
        FrameDecoder().feed(frame)


def test_decoder_rejects_negative_content_length() -> None:
    frame = b"Content-Length: -1\r\nProtocol-Version: 1\r\n\r\n"

    with pytest.raises(FramingError):
        FrameDecoder().feed(frame)


def test_decoder_rejects_oversized_declared_body_before_receiving_it() -> None:
    frame = f"Content-Length: {MAX_BODY_BYTES + 1}\r\nProtocol-Version: 1\r\n\r\n".encode()

    with pytest.raises(FramingError):
        FrameDecoder().feed(frame)


def test_decoder_wraps_extremely_long_decimal_content_length() -> None:
    frame = b"Content-Length: " + (b"9" * 5000) + b"\r\nProtocol-Version: 1\r\n\r\n"

    with pytest.raises(FramingError):
        FrameDecoder().feed(frame)


@pytest.mark.parametrize("version", ["2", "one", "1.0", "+1"])
def test_decoder_rejects_invalid_protocol_version_header(version: str) -> None:
    body = (
        IpcMessage(message_id="m1", sequence=1, project_id="p", type="event")
        .model_dump_json()
        .encode("utf-8")
    )
    frame = f"Content-Length: {len(body)}\r\nProtocol-Version: {version}\r\n\r\n".encode() + body

    with pytest.raises(FramingError):
        FrameDecoder().feed(frame)


def test_decoder_wraps_invalid_utf8_body_without_exposing_contents() -> None:
    frame = b"Content-Length: 1\r\nProtocol-Version: 1\r\n\r\n\xff"

    with pytest.raises(FramingError) as error:
        FrameDecoder().feed(frame)

    assert "ff" not in str(error.value).lower()
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__ is True


@pytest.mark.parametrize(
    "body",
    [
        b'{"secret":"do-not-leak"',
        b'{"message_id":"m1","sequence":1,"project_id":"p","type":"unknown"}',
    ],
)
def test_decoder_wraps_invalid_json_or_message_without_exposing_body(body: bytes) -> None:
    frame = f"Content-Length: {len(body)}\r\nProtocol-Version: 1\r\n\r\n".encode() + body

    with pytest.raises(FramingError) as error:
        FrameDecoder().feed(frame)

    assert "secret" not in str(error.value).lower()
    assert "unknown" not in str(error.value).lower()
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__ is True


def test_encode_content_length_counts_utf8_bytes() -> None:
    message = IpcMessage(
        message_id="m1",
        sequence=1,
        project_id="p",
        type="event",
        payload={"text": "你好"},
    )
    body = message.model_dump_json().encode("utf-8")

    assert encode_frame(message) == (
        f"Content-Length: {len(body)}\r\nProtocol-Version: 1\r\n\r\n".encode() + body
    )


def test_decoder_accepts_case_insensitive_header_names() -> None:
    message = IpcMessage(message_id="m1", sequence=1, project_id="p", type="ack")
    body = message.model_dump_json().encode("utf-8")
    frame = f"content-length: {len(body)}\r\nprotocol-version: 1\r\n\r\n".encode() + body

    assert FrameDecoder().feed(frame) == [message]


def test_decoder_rejects_terminated_oversized_header() -> None:
    body = (
        IpcMessage(message_id="m1", sequence=1, project_id="p", type="event")
        .model_dump_json()
        .encode("utf-8")
    )
    padding = b" " * MAX_HEADER_BYTES
    frame = (
        b"Content-Length:"
        + padding
        + str(len(body)).encode()
        + b"\r\nProtocol-Version: 1\r\n\r\n"
        + body
    )

    with pytest.raises(FramingError):
        FrameDecoder().feed(frame)


@pytest.mark.parametrize("delimiter_prefix_length", [1, 2, 3])
def test_decoder_accepts_exact_max_header_with_split_delimiter(
    delimiter_prefix_length: int,
) -> None:
    message = IpcMessage(message_id="m1", sequence=1, project_id="p", type="event")
    body = message.model_dump_json().encode("utf-8")
    fixed_header = b"Content-Length:" + str(len(body)).encode() + b"\r\nProtocol-Version: 1"
    header = (
        b"Content-Length:"
        + (b" " * (MAX_HEADER_BYTES - len(fixed_header)))
        + str(len(body)).encode()
        + b"\r\nProtocol-Version: 1"
    )
    delimiter = b"\r\n\r\n"
    decoder = FrameDecoder()

    assert len(header) == MAX_HEADER_BYTES
    assert FrameDecoder().feed(header + delimiter + body) == [message]
    assert decoder.feed(header + delimiter[:delimiter_prefix_length]) == []
    assert decoder.feed(delimiter[delimiter_prefix_length:] + body) == [message]


@pytest.mark.parametrize("header_shortfall", [1, 2, 3])
@pytest.mark.parametrize("delimiter_prefix_length", [1, 2, 3])
def test_decoder_accepts_near_max_header_with_split_delimiter(
    header_shortfall: int,
    delimiter_prefix_length: int,
) -> None:
    message = IpcMessage(message_id="m1", sequence=1, project_id="p", type="event")
    body = message.model_dump_json().encode("utf-8")
    fixed_header = b"Content-Length:" + str(len(body)).encode() + b"\r\nProtocol-Version: 1"
    target_header_length = MAX_HEADER_BYTES - header_shortfall
    header = (
        b"Content-Length:"
        + (b" " * (target_header_length - len(fixed_header)))
        + str(len(body)).encode()
        + b"\r\nProtocol-Version: 1"
    )
    delimiter = b"\r\n\r\n"
    decoder = FrameDecoder()

    assert len(header) == target_header_length
    assert decoder.feed(header + delimiter[:delimiter_prefix_length]) == []
    assert decoder.feed(delimiter[delimiter_prefix_length:] + body) == [message]


def test_decoder_clears_buffer_after_error_and_accepts_fresh_frame() -> None:
    decoder = FrameDecoder()
    invalid = b"Content-Length: 1\r\nProtocol-Version: 1\r\n\r\nx"
    valid_message = IpcMessage(message_id="m1", sequence=1, project_id="p", type="ack")

    with pytest.raises(FramingError):
        decoder.feed(invalid + encode_frame(valid_message))

    assert decoder.feed(encode_frame(valid_message)) == [valid_message]


def test_decoder_parses_header_once_while_body_arrives_byte_by_byte() -> None:
    class CountingFrameDecoder(FrameDecoder):
        header_parse_count = 0

        def _parse_header(self, header: bytes) -> int:
            self.header_parse_count += 1
            return super()._parse_header(header)

    message = IpcMessage(
        message_id="m1",
        sequence=1,
        project_id="p",
        type="event",
        payload={"text": "x" * 4096},
    )
    body = message.model_dump_json().encode("utf-8")
    fixed_header = b"Content-Length:" + str(len(body)).encode() + b"\r\nProtocol-Version: 1"
    header = (
        b"Content-Length:"
        + (b" " * (MAX_HEADER_BYTES - len(fixed_header)))
        + str(len(body)).encode()
        + b"\r\nProtocol-Version: 1\r\n\r\n"
    )
    decoder = CountingFrameDecoder()
    result: list[IpcMessage] = []

    for byte in header + body:
        result.extend(decoder.feed(bytes([byte])))

    assert result == [message]
    assert decoder.header_parse_count == 1


def test_decoder_advances_search_offset_for_incomplete_header() -> None:
    class TrackingBuffer(bytearray):
        searches: list[tuple[int, int]]

        def __init__(self) -> None:
            super().__init__()
            self.searches = []

        def find(  # type: ignore[override]
            self,
            sub: Any,
            start: int = 0,
            end: int | None = None,
        ) -> int:
            self.searches.append((start, len(self)))
            if end is None:
                return super().find(sub, start)
            return super().find(sub, start, end)

    message = IpcMessage(message_id="m1", sequence=1, project_id="p", type="event")
    body = message.model_dump_json().encode("utf-8")
    fixed_header = b"Content-Length:" + str(len(body)).encode() + b"\r\nProtocol-Version: 1"
    header_length = 1024
    header = (
        b"Content-Length:"
        + (b" " * (header_length - len(fixed_header)))
        + str(len(body)).encode()
        + b"\r\nProtocol-Version: 1\r\n\r\n"
    )
    tracking_buffer = TrackingBuffer()
    decoder = FrameDecoder()
    decoder._buffer = tracking_buffer
    result: list[IpcMessage] = []

    for byte in header + body:
        result.extend(decoder.feed(bytes([byte])))

    assert result == [message]
    assert any(start > 0 for start, _ in tracking_buffer.searches)
    assert all(length - start <= 4 for start, length in tracking_buffer.searches)


def test_decoder_compacts_once_for_many_coalesced_frames() -> None:
    class CountingCompactionDecoder(FrameDecoder):
        compaction_count = 0

        def _compact_buffer(self, cursor: int) -> None:
            self.compaction_count += 1
            super()._compact_buffer(cursor)

    messages = [
        IpcMessage(message_id=f"m{sequence}", sequence=sequence, project_id="p", type="ack")
        for sequence in range(100)
    ]
    decoder = CountingCompactionDecoder()

    assert decoder.feed(b"".join(encode_frame(message) for message in messages)) == messages
    assert decoder.compaction_count == 1
