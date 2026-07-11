from typing import Never

from pydantic import ValidationError
from pydantic_core import PydanticSerializationError

from agent_platform.interfaces.ipc.messages import IpcMessage

_HEADER_TERMINATOR = b"\r\n\r\n"
MAX_HEADER_BYTES = 8 * 1024
MAX_BODY_BYTES = 1024 * 1024


class FramingError(ValueError):
    """Raised when an IPC frame is invalid or exceeds transport limits."""


def encode_frame(message: IpcMessage) -> bytes:
    candidate = {
        "protocol_version": message.protocol_version,
        "message_id": message.message_id,
        "correlation_id": message.correlation_id,
        "sequence": message.sequence,
        "project_id": message.project_id,
        "task_id": message.task_id,
        "type": message.type,
        "timestamp": message.timestamp,
        "payload": message.payload,
    }
    try:
        validated_message = IpcMessage.model_validate(candidate, strict=True)
        body = validated_message.model_dump_json().encode("utf-8")
    except (PydanticSerializationError, ValidationError, ValueError):
        body = None
    if body is None:
        raise FramingError("IPC frame body is invalid") from None
    if len(body) > MAX_BODY_BYTES:
        raise FramingError("IPC frame body exceeds maximum size")
    header = f"Content-Length: {len(body)}\r\nProtocol-Version: 1\r\n\r\n".encode("ascii")
    return header + body


class FrameDecoder:
    def __init__(self) -> None:
        self._buffer = bytearray()
        self._expected_body_length: int | None = None
        self._header_scan_offset = 0

    def _fail(self, message: str) -> Never:
        self._buffer.clear()
        self._expected_body_length = None
        self._header_scan_offset = 0
        raise FramingError(message) from None

    def _parse_header(self, header_bytes: bytes) -> int:
        try:
            header = header_bytes.decode("ascii")
        except UnicodeDecodeError:
            header = None
        if header is None:
            self._fail("IPC frame header is not ASCII")
        headers: dict[str, str] = {}
        header_lines = header.split("\r\n")
        if len(header_lines) != 2 or any(not line for line in header_lines):
            self._fail("IPC frame header must contain exactly two nonempty lines")
        for line in header_lines:
            if line.count(":") != 1:
                self._fail("IPC frame header line is malformed")
            name, raw_value = line.split(":", 1)
            value = raw_value.strip()
            if not name or name != name.strip() or not value:
                self._fail("IPC frame header line is malformed")
            normalized_name = name.lower()
            if normalized_name in headers:
                self._fail("IPC frame contains a duplicate header")
            headers[normalized_name] = value
        required_headers = {"content-length", "protocol-version"}
        if required_headers - headers.keys():
            self._fail("IPC frame is missing a required header")
        if headers.keys() - required_headers:
            self._fail("IPC frame contains an unknown header")
        if headers["protocol-version"] != "1":
            self._fail("IPC frame protocol version is unsupported")
        content_length_value = headers["content-length"]
        if not content_length_value.isdecimal():
            self._fail("IPC frame content length is invalid")
        normalized_length = content_length_value.lstrip("0") or "0"
        maximum_length = str(MAX_BODY_BYTES)
        if len(normalized_length) > len(maximum_length) or (
            len(normalized_length) == len(maximum_length) and normalized_length > maximum_length
        ):
            self._fail("IPC frame body exceeds maximum size")
        return int(normalized_length)

    def _partial_delimiter_length(self) -> int:
        maximum_partial_length = min(
            len(_HEADER_TERMINATOR) - 1,
            len(self._buffer),
        )
        for suffix_length in range(maximum_partial_length, 0, -1):
            suffix = bytes(self._buffer[-suffix_length:])
            if _HEADER_TERMINATOR.startswith(suffix):
                return suffix_length
        return 0

    def _compact_buffer(self, cursor: int) -> None:
        if cursor:
            del self._buffer[:cursor]
            self._header_scan_offset = max(0, self._header_scan_offset - cursor)

    def feed(self, chunk: bytes) -> list[IpcMessage]:
        self._buffer.extend(chunk)
        messages: list[IpcMessage] = []
        cursor = 0

        while True:
            if self._expected_body_length is None:
                search_start = max(cursor, self._header_scan_offset)
                header_end = self._buffer.find(_HEADER_TERMINATOR, search_start)
                if header_end < 0:
                    partial_delimiter_length = self._partial_delimiter_length()
                    candidate_header_length = len(self._buffer) - cursor - partial_delimiter_length
                    if candidate_header_length > MAX_HEADER_BYTES:
                        self._fail("IPC frame header exceeds maximum size")
                    self._header_scan_offset = max(cursor, len(self._buffer) - 3)
                    break
                header_length = header_end - cursor
                if header_length > MAX_HEADER_BYTES:
                    self._fail("IPC frame header exceeds maximum size")
                header = bytes(self._buffer[cursor:header_end])
                self._expected_body_length = self._parse_header(header)
                self._header_scan_offset = 0
                cursor = header_end + len(_HEADER_TERMINATOR)

            frame_end = cursor + self._expected_body_length
            if len(self._buffer) < frame_end:
                break

            body = bytes(self._buffer[cursor:frame_end])
            cursor = frame_end
            self._expected_body_length = None
            try:
                messages.append(IpcMessage.model_validate_json(body))
            except ValidationError:
                self._fail("IPC frame body is invalid")

        self._compact_buffer(cursor)
        return messages
