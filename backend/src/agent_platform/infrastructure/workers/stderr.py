from __future__ import annotations

import codecs
import hashlib
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

_SAFE_DIAGNOSTIC = re.compile(
    r"worker (bootstrap|argument|protocol|internal) error(?:\: ([A-Za-z_][A-Za-z0-9_]{0,63}))?\Z"
)


@dataclass(frozen=True, slots=True)
class SafeWorkerDiagnostic:
    category: Literal["bootstrap_error", "argument_error", "protocol_error", "internal_error"]
    exception_type: str | None


@dataclass(frozen=True, slots=True)
class OpaqueWorkerStderr:
    byte_count: int
    sha256: str
    truncated: bool
    invalid_utf8: bool


WorkerStderrEvidence = SafeWorkerDiagnostic | OpaqueWorkerStderr


class WorkerStderrDecoder:
    def __init__(self, max_line_bytes: int = 4096) -> None:
        if max_line_bytes < 1:
            raise ValueError("max line bytes must be positive")
        self._max_line_bytes = max_line_bytes
        self._retained = bytearray()
        self._byte_count = 0
        self._digest = hashlib.sha256()
        self._utf8_decoder = codecs.getincrementaldecoder("utf-8")("strict")
        self._invalid_utf8 = False

    @property
    def retained_byte_count(self) -> int:
        return len(self._retained)

    def _consume(self, data: bytes) -> None:
        self._byte_count += len(data)
        self._digest.update(data)
        remaining = self._max_line_bytes - len(self._retained)
        if remaining > 0:
            self._retained.extend(data[:remaining])
        if not self._invalid_utf8:
            try:
                self._utf8_decoder.decode(data, final=False)
            except UnicodeDecodeError:
                self._invalid_utf8 = True

    def _reset(self) -> None:
        self._retained.clear()
        self._byte_count = 0
        self._digest = hashlib.sha256()
        self._utf8_decoder = codecs.getincrementaldecoder("utf-8")("strict")
        self._invalid_utf8 = False

    def _finish_line(self) -> WorkerStderrEvidence:
        if not self._invalid_utf8:
            try:
                self._utf8_decoder.decode(b"", final=True)
            except UnicodeDecodeError:
                self._invalid_utf8 = True
        retained = bytes(self._retained)
        grammar_bytes = retained[:-1] if retained.endswith(b"\r") else retained
        truncated = self._byte_count > self._max_line_bytes
        if not truncated and not self._invalid_utf8:
            text = grammar_bytes.decode("utf-8")
            match = _SAFE_DIAGNOSTIC.fullmatch(text)
            if match is not None:
                name, exception_type = match.groups()
                if name in {"bootstrap", "argument"} and exception_type is not None:
                    match = None
                elif name in {"protocol", "internal"} and exception_type is None:
                    match = None
                if match is not None:
                    evidence = SafeWorkerDiagnostic(
                        category=f"{name}_error",  # type: ignore[arg-type]
                        exception_type=exception_type,
                    )
                    self._reset()
                    return evidence
        opaque_evidence = OpaqueWorkerStderr(
            byte_count=self._byte_count,
            sha256=self._digest.hexdigest(),
            truncated=truncated,
            invalid_utf8=self._invalid_utf8,
        )
        self._reset()
        return opaque_evidence

    def feed(self, data: bytes) -> list[WorkerStderrEvidence]:
        evidence: list[WorkerStderrEvidence] = []
        start = 0
        while True:
            newline = data.find(b"\n", start)
            if newline < 0:
                self._consume(data[start:])
                break
            self._consume(data[start:newline])
            evidence.append(self._finish_line())
            start = newline + 1
        return evidence

    def finish(self) -> list[WorkerStderrEvidence]:
        if self._byte_count == 0:
            return []
        return [self._finish_line()]


class WorkerStderrReporter:
    def __init__(
        self,
        logger: Any,
        *,
        max_records_per_window: int = 32,
        window_seconds: float = 1.0,
        clock: Any = time.monotonic,
    ) -> None:
        if max_records_per_window < 1 or window_seconds <= 0:
            raise ValueError("worker stderr rate limit is invalid")
        self._logger = logger
        self._max_records = max_records_per_window
        self._window_seconds = window_seconds
        self._clock = clock
        self._window_started = float(clock())
        self._emitted = 0
        self._suppressed_lines = 0
        self._suppressed_bytes = 0

    def _flush_for_new_window(self, now: float) -> None:
        if now - self._window_started < self._window_seconds:
            return
        self.flush_summary()
        self._window_started = now
        self._emitted = 0

    def emit(self, evidence: WorkerStderrEvidence) -> None:
        now = float(self._clock())
        self._flush_for_new_window(now)
        byte_count = evidence.byte_count if isinstance(evidence, OpaqueWorkerStderr) else 0
        if self._emitted >= self._max_records:
            self._suppressed_lines += 1
            self._suppressed_bytes += byte_count
            return
        self._emitted += 1
        if isinstance(evidence, SafeWorkerDiagnostic):
            self._logger.info(
                "worker_diagnostic",
                category=evidence.category,
                exception_type=evidence.exception_type,
            )
        else:
            self._logger.info(
                "worker_stderr_opaque",
                byte_count=evidence.byte_count,
                sha256=evidence.sha256,
                truncated=evidence.truncated,
                invalid_utf8=evidence.invalid_utf8,
            )

    def emit_all(self, evidence: Iterable[WorkerStderrEvidence]) -> None:
        for item in evidence:
            self.emit(item)

    def flush_summary(self) -> None:
        if self._suppressed_lines == 0:
            return
        self._logger.warning(
            "worker_stderr_suppressed",
            suppressed_lines=self._suppressed_lines,
            suppressed_bytes=self._suppressed_bytes,
        )
        self._suppressed_lines = 0
        self._suppressed_bytes = 0

    def reader_failed(self, exception_type: str) -> None:
        self._logger.error(
            "worker_stderr_reader_failed",
            exception_type=exception_type,
        )
