from datetime import datetime

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


def test_decoder_rejects_oversized_unterminated_header() -> None:
    decoder = FrameDecoder()

    with pytest.raises(FramingError):
        decoder.feed(b"x" * (MAX_HEADER_BYTES + 4))


def test_decoder_rejects_non_ascii_header() -> None:
    decoder = FrameDecoder()
    frame = b"Content-Length: 2\r\nProtocol-Version: 1\r\nX-\xff: value\r\n\r\n{}"

    with pytest.raises(FramingError):
        decoder.feed(frame)


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


def test_decoder_clears_buffer_after_error_and_accepts_fresh_frame() -> None:
    decoder = FrameDecoder()
    invalid = b"Content-Length: 1\r\nProtocol-Version: 1\r\n\r\nx"
    valid_message = IpcMessage(message_id="m1", sequence=1, project_id="p", type="ack")

    with pytest.raises(FramingError):
        decoder.feed(invalid + encode_frame(valid_message))

    assert decoder.feed(encode_frame(valid_message)) == [valid_message]
