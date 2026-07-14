import hashlib

from agent_platform.infrastructure.workers.stderr import (
    OpaqueWorkerStderr,
    SafeWorkerDiagnostic,
    WorkerStderrDecoder,
    WorkerStderrReporter,
)


class _RecordingLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, object]]] = []

    def info(self, event: str, **values: object) -> None:
        self.events.append(("info", event, values))

    def warning(self, event: str, **values: object) -> None:
        self.events.append(("warning", event, values))

    def error(self, event: str, **values: object) -> None:
        self.events.append(("error", event, values))


def test_decoder_parses_safe_diagnostic_across_chunks() -> None:
    decoder = WorkerStderrDecoder()

    assert decoder.feed(b"worker protocol") == []
    evidence = decoder.feed(b" error: FramingError\r\n")

    assert evidence == [
        SafeWorkerDiagnostic(category="protocol_error", exception_type="FramingError")
    ]


def test_decoder_reduces_unknown_content_to_opaque_evidence() -> None:
    raw = b"unsafe secret payload"
    decoder = WorkerStderrDecoder()

    evidence = decoder.feed(raw + b"\n")[0]

    assert evidence == OpaqueWorkerStderr(
        byte_count=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        truncated=False,
        invalid_utf8=False,
    )
    assert raw.decode() not in repr(evidence)


def test_decoder_bounds_multi_megabyte_unterminated_line() -> None:
    raw = b"x" * (2 * 1024 * 1024)
    decoder = WorkerStderrDecoder(max_line_bytes=4096)

    assert decoder.feed(raw) == []
    assert decoder.retained_byte_count == 4096
    evidence = decoder.finish()[0]

    assert isinstance(evidence, OpaqueWorkerStderr)
    assert evidence.byte_count == len(raw)
    assert evidence.sha256 == hashlib.sha256(raw).hexdigest()
    assert evidence.truncated is True
    assert decoder.retained_byte_count == 0


def test_decoder_marks_invalid_utf8_without_retaining_raw_bytes() -> None:
    decoder = WorkerStderrDecoder()

    evidence = decoder.feed(b"\xffsecret\n")[0]

    assert isinstance(evidence, OpaqueWorkerStderr)
    assert evidence.invalid_utf8 is True
    assert "secret" not in repr(evidence)


def test_reporter_rate_limits_detail_and_emits_payload_free_summary() -> None:
    logger = _RecordingLogger()
    reporter = WorkerStderrReporter(logger, max_records_per_window=1, window_seconds=10)
    evidence = OpaqueWorkerStderr(10, "a" * 64, False, False)

    reporter.emit(evidence)
    reporter.emit(evidence)
    reporter.flush_summary()

    assert logger.events == [
        (
            "info",
            "worker_stderr_opaque",
            {
                "byte_count": 10,
                "sha256": "a" * 64,
                "truncated": False,
                "invalid_utf8": False,
            },
        ),
        (
            "warning",
            "worker_stderr_suppressed",
            {"suppressed_lines": 1, "suppressed_bytes": 10},
        ),
    ]
