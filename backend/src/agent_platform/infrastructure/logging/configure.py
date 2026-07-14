from __future__ import annotations

import hashlib
import json
import logging
import queue
import sys
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Any, Final, TextIO, cast

import structlog
from structlog.typing import Processor

from agent_platform.infrastructure.logging.files import SafeRotatingFileHandler
from agent_platform.infrastructure.redaction import redact_text, sanitize_mapping

_UVICORN_LOGGERS: Final[tuple[str, ...]] = (
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "uvicorn.asgi",
)
_STOP = object()
_STANDARD_LOG_RECORD_KEYS: Final[frozenset[str]] = frozenset(logging.makeLogRecord({}).__dict__) | {
    "message",
    "asctime",
}


class LoggingDrainTimeout(RuntimeError):
    """Raised when the logging writer cannot stop by its deadline."""


class LoggingWriterError(RuntimeError):
    """Raised when the logging writer terminates unexpectedly."""


def _numeric_level(level: str) -> int:
    numeric_level = logging.getLevelNamesMapping().get(level.upper())
    if numeric_level is None:
        raise ValueError(f"invalid log level: {level}")
    return numeric_level


def _close_handlers(logger: logging.Logger) -> None:
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()


def prepare_uvicorn_logging(level: str) -> None:
    numeric_level = _numeric_level(level)
    root_logger = logging.getLogger()
    _close_handlers(root_logger)
    root_logger.setLevel(numeric_level)
    root_logger.addHandler(logging.NullHandler())
    for name in _UVICORN_LOGGERS:
        logger = logging.getLogger(name)
        _close_handlers(logger)
        logger.setLevel(numeric_level)
        logger.propagate = True


def redact_secrets(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], sanitize_mapping(event_dict))


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _safe_message(record: logging.LogRecord) -> object:
    if isinstance(record.msg, Mapping):
        return sanitize_mapping(record.msg)
    if not isinstance(record.msg, str):
        return "unsupported_log_message"
    message = redact_text(record.msg)
    if not record.args:
        return message
    safe_args: object
    if isinstance(record.args, Mapping):
        safe_args = sanitize_mapping(record.args)
    elif isinstance(record.args, tuple):
        safe_args = tuple(
            sanitize_mapping(item) if isinstance(item, Mapping) else _safe_scalar(item)
            for item in record.args
        )
    else:
        safe_args = _safe_scalar(record.args)
    try:
        return redact_text(message % safe_args)
    except (KeyError, TypeError, ValueError):
        return "log_format_error"


def _safe_scalar(value: object) -> object:
    if isinstance(value, Mapping):
        return sanitize_mapping(value)
    if isinstance(value, list):
        return [_safe_scalar(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_safe_scalar(item) for item in value)
    return sanitize_mapping({"value": value})["value"]


def _event_from_record(record: logging.LogRecord) -> dict[str, object]:
    if isinstance(record.msg, Mapping) and (
        bool(record.msg.get("_from_structlog")) or hasattr(record, "_logger")
    ):
        event = sanitize_mapping(record.msg)
        event.pop("_record", None)
        event.pop("_from_structlog", None)
        event.setdefault("timestamp", _timestamp())
        event.setdefault("level", record.levelname.lower())
        event.setdefault("logger", record.name)
        event.setdefault("event", "structured_event")
    else:
        event = {
            "timestamp": _timestamp(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": _safe_message(record),
        }
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_LOG_RECORD_KEYS and not key.startswith("_")
        }
        event.update(sanitize_mapping(extras))
    if record.exc_info is not None and record.exc_info[0] is not None:
        event["exception_type"] = record.exc_info[0].__name__
    return sanitize_mapping(event)


def _render_bounded_json(event: Mapping[Any, Any], max_record_bytes: int) -> bytes:
    safe_event = sanitize_mapping(event)
    rendered = json.dumps(
        safe_event,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if len(rendered) + 1 <= max_record_bytes:
        return rendered + b"\n"
    fallback = {
        "timestamp": safe_event.get("timestamp", _timestamp()),
        "level": safe_event.get("level", "warning"),
        "logger": safe_event.get("logger", "agent_platform.logging"),
        "event": "log_record_truncated",
        "original_utf8_bytes": len(rendered),
        "original_sha256": hashlib.sha256(rendered).hexdigest(),
        "truncated": True,
    }
    bounded = (
        json.dumps(
            fallback,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    if len(bounded) > max_record_bytes:
        raise ValueError("log record limit is too small")
    return bounded


class _BoundedQueueHandler(logging.Handler):
    def __init__(self, capacity: int, max_record_bytes: int) -> None:
        super().__init__()
        self.records: queue.Queue[bytes | object] = queue.Queue(maxsize=capacity)
        self._max_record_bytes = max_record_bytes
        self._state_lock = threading.Lock()
        self._accepting = True
        self._dropped = 0

    @property
    def capacity(self) -> int:
        return self.records.maxsize

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = _render_bounded_json(_event_from_record(record), self._max_record_bytes)
        except BaseException:
            line = _render_bounded_json(
                {
                    "timestamp": _timestamp(),
                    "level": "error",
                    "logger": "agent_platform.logging",
                    "event": "log_record_sanitization_failed",
                },
                self._max_record_bytes,
            )
        with self._state_lock:
            if not self._accepting:
                return
            try:
                self.records.put_nowait(line)
            except queue.Full:
                self._dropped += 1

    def stop_admission(self) -> None:
        with self._state_lock:
            self._accepting = False

    def take_dropped(self) -> int:
        with self._state_lock:
            dropped = self._dropped
            self._dropped = 0
            return dropped


class _LogWriter(threading.Thread):
    def __init__(
        self,
        handler: _BoundedQueueHandler,
        file_handler: SafeRotatingFileHandler,
        stderr: TextIO,
        max_record_bytes: int,
    ) -> None:
        super().__init__(name="backend-log-writer", daemon=True)
        self._handler = handler
        self._file_handler = file_handler
        self._stderr = stderr
        self._max_record_bytes = max_record_bytes
        self._stop_requested = threading.Event()
        self.failure_type: str | None = None

    def request_stop(self) -> None:
        self._stop_requested.set()

    def _write_line(self, line: bytes) -> None:
        self._stderr.write(line.decode("utf-8"))
        self._stderr.flush()
        self._file_handler.write_line(line)

    def _write_overflow(self) -> None:
        dropped = self._handler.take_dropped()
        if dropped:
            self._write_line(
                _render_bounded_json(
                    {
                        "timestamp": _timestamp(),
                        "level": "warning",
                        "logger": "agent_platform.logging",
                        "event": "logging_queue_overflow",
                        "dropped_records": dropped,
                    },
                    self._max_record_bytes,
                )
            )

    def run(self) -> None:
        try:
            while True:
                try:
                    item = self._handler.records.get(timeout=0.05)
                except queue.Empty:
                    if self._stop_requested.is_set() and self._handler.records.empty():
                        self._write_overflow()
                        return
                    continue
                if item is _STOP:
                    return
                self._write_overflow()
                if not isinstance(item, bytes):
                    raise TypeError("logging queue item is invalid")
                self._write_line(item)
        except BaseException as error:
            self.failure_type = type(error).__name__
        finally:
            try:
                self._file_handler.close()
            except BaseException:
                if self.failure_type is None:
                    self.failure_type = "HandlerCloseError"


@dataclass(slots=True)
class LoggingRuntime:
    queue_capacity: int
    _handler: _BoundedQueueHandler = field(repr=False)
    _writer: _LogWriter = field(repr=False)
    _shutdown_drain_timeout: timedelta = field(repr=False)
    _closed: bool = field(default=False, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def close(self) -> None:
        with self._lock:
            if self._closed and not self._writer.is_alive():
                if self._writer.failure_type is not None:
                    raise LoggingWriterError("logging writer failed")
                return
            self._closed = True
            self._handler.stop_admission()
            root_logger = logging.getLogger()
            if self._handler in root_logger.handlers:
                root_logger.removeHandler(self._handler)
            if not root_logger.handlers:
                root_logger.addHandler(logging.NullHandler())
            self._writer.request_stop()
            self._writer.join(self._shutdown_drain_timeout.total_seconds())
            if self._writer.is_alive():
                raise LoggingDrainTimeout("logging writer did not stop")
            self._handler.close()
            if self._writer.failure_type is not None:
                raise LoggingWriterError("logging writer failed")

    def __enter__(self) -> LoggingRuntime:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        self.close()


def configure_logging(
    log_root: Path,
    level: str,
    *,
    max_bytes: int = 10 * 1024 * 1024,
    max_record_bytes: int = 32 * 1024,
    retained_file_count: int = 5,
    retention_age: timedelta = timedelta(days=30),
    queue_capacity: int = 4096,
    shutdown_drain_timeout: timedelta = timedelta(seconds=1),
) -> LoggingRuntime:
    numeric_level = _numeric_level(level)
    if max_record_bytes > max_bytes:
        raise ValueError("log record limit must not exceed file limit")

    redaction_processor = cast(Processor, redact_secrets)
    structlog.configure(
        processors=[
            redaction_processor,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )

    file_handler = SafeRotatingFileHandler(
        log_root,
        max_bytes=max_bytes,
        retained_file_count=retained_file_count,
        retention_age=retention_age,
    )
    queue_handler = _BoundedQueueHandler(queue_capacity, max_record_bytes)
    prepare_uvicorn_logging(level)
    root_logger = logging.getLogger()
    _close_handlers(root_logger)
    root_logger.setLevel(numeric_level)
    root_logger.addHandler(queue_handler)
    for name in _UVICORN_LOGGERS:
        logger = logging.getLogger(name)
        _close_handlers(logger)
        logger.setLevel(numeric_level)
        logger.propagate = True

    writer = _LogWriter(queue_handler, file_handler, sys.stderr, max_record_bytes)
    writer.start()
    return LoggingRuntime(
        queue_capacity=queue_capacity,
        _handler=queue_handler,
        _writer=writer,
        _shutdown_drain_timeout=shutdown_drain_timeout,
    )
