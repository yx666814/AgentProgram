from typing import Never

from pydantic import ValidationError

from agent_platform.interfaces.ipc.messages import IpcMessage

_HEADER_TERMINATOR = b"\r\n\r\n"
MAX_HEADER_BYTES = 8 * 1024
MAX_BODY_BYTES = 1024 * 1024
_MAX_UNTERMINATED_HEADER_BYTES = MAX_HEADER_BYTES + len(_HEADER_TERMINATOR) - 1


class FramingError(ValueError):
    """Raised when an IPC frame is invalid or exceeds transport limits."""


def encode_frame(message: IpcMessage) -> bytes:
    body = message.model_dump_json().encode("utf-8")
    if len(body) > MAX_BODY_BYTES:
        raise FramingError("IPC frame body exceeds maximum size")
    header = f"Content-Length: {len(body)}\r\nProtocol-Version: 1\r\n\r\n".encode("ascii")
    return header + body


class FrameDecoder:
    def __init__(self) -> None:
        self._buffer = bytearray()

    def _fail(self, message: str, error: Exception | None = None) -> Never:
        self._buffer.clear()
        if error is None:
            raise FramingError(message) from None
        raise FramingError(message) from error

    def feed(self, chunk: bytes) -> list[IpcMessage]:
        self._buffer.extend(chunk)
        messages: list[IpcMessage] = []

        while True:
            header_end = self._buffer.find(_HEADER_TERMINATOR)
            if header_end < 0:
                if len(self._buffer) > _MAX_UNTERMINATED_HEADER_BYTES:
                    self._fail("IPC frame header exceeds maximum size")
                return messages
            if header_end > MAX_HEADER_BYTES:
                self._fail("IPC frame header exceeds maximum size")

            try:
                header = self._buffer[:header_end].decode("ascii")
            except UnicodeDecodeError as error:
                self._fail("IPC frame header is not ASCII", error)
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
            content_length = int(normalized_length)
            body_start = header_end + len(_HEADER_TERMINATOR)
            frame_end = body_start + content_length
            if len(self._buffer) < frame_end:
                return messages

            body = bytes(self._buffer[body_start:frame_end])
            del self._buffer[:frame_end]
            try:
                messages.append(IpcMessage.model_validate_json(body))
            except ValidationError:
                self._fail("IPC frame body is invalid")
