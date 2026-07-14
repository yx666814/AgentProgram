# Backend Stage 1E Runtime Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist bounded, rotating, secret-redacted Backend JSONL logs and convert Worker stderr into safe structured diagnostics or payload-free evidence.

**Architecture:** One shared redaction registry sanitizes API details, stdlib logs, structlog events, and registered secret values. The root logger converts each record into one bounded, fully redacted, immutable UTF-8 JSON line using CPU-only safe primitives, then performs a non-blocking `put_nowait()` into a bounded queue; it never retains the original `LogRecord`, arguments, exception, or secret. One dedicated writer thread owns synchronized stderr/file I/O, overflow summaries, and the close deadline. `WorkerSupervisor` keeps draining stderr continuously, but a bounded decoder stores only approved first-party diagnostics or byte count, SHA-256, and safety flags, so slow or blocked disk I/O cannot stall IPC.

**Tech Stack:** Python 3.12, asyncio, logging, structlog, `queue`, `threading`, Pydantic Settings, hashlib, pytest, Ruff, mypy.

**Process override:** The user explicitly requested implementation-first testing for Stage 1E–1I. Implement each approved behavior before adding its focused tests; all tests and quality gates remain mandatory.

**Command convention:** Every command block runs from `D:\AgentProgram\.worktrees\backend-stage1\backend`. Git commands use `git -C ..` so repository-root paths remain exact.

---

## File Map and Responsibilities

```text
backend/src/agent_platform/
|- config/settings.py
|  `- validated rotation, record-size, queue-capacity, and close-deadline settings
|- infrastructure/redaction.py
|  `- sensitive keys, ref-counted known-secret registry, recursive safe rendering
|- infrastructure/logging/
|  |- configure.py
|  |  `- bounded JSON formatter, queue handler, writer thread, Uvicorn adoption, LoggingRuntime.close()
|  `- files.py
|     `- handle-verified active file, safe rotation, and application-owned log retention
|- infrastructure/workers/
|  |- stderr.py
|  |  `- bounded line decoder, approved grammar, opaque evidence, rate limiter
|  `- supervisor.py
|     `- continuously drain stderr and emit structured evidence
|- interfaces/api/errors.py
|  `- consume shared redaction instead of a second sensitive-key list
|- main.py
|  `- disable Uvicorn's independent logging configuration
`- bootstrap/lifespan.py
   `- register session token and close logging after database disposal

backend/tests/
|- unit/test_redaction.py
|- unit/test_log_redaction.py
|- unit/test_worker_stderr.py
|- process/test_logging_runtime.py
|- process/test_uvicorn_logging.py
|- process/test_worker_supervisor.py
|- integration/test_application_lifespan.py
`- contract/test_system_api.py

backend/README.md
```

## Frozen Interfaces

```python
# agent_platform.infrastructure.redaction
class SecretRegistration:
    def close(self) -> None: ...

def register_known_secret(value: str) -> SecretRegistration: ...
def redact_text(value: str) -> str: ...
def sanitize_mapping(value: Mapping[object, object]) -> dict[str, object]: ...

# agent_platform.infrastructure.logging.configure
@dataclass(slots=True)
class LoggingRuntime:
    queue_capacity: int
    def close(self) -> None: ...

def configure_logging(
    log_root: Path,
    level: str,
    *,
    max_bytes: int,
    max_record_bytes: int,
    retained_file_count: int,
    retention_age: timedelta,
    queue_capacity: int,
    shutdown_drain_timeout: timedelta,
) -> LoggingRuntime: ...

def prepare_uvicorn_logging(level: str) -> None: ...

# agent_platform.infrastructure.logging.files
def prune_stale_log_files(
    log_root: Path,
    *,
    retention_age: timedelta,
    now: datetime | None = None,
) -> None: ...
```

## Explicit Boundary with Stage 1F

- Stage 1E may add logging imports and replace only `WorkerSupervisor._drain_stderr()` plus stderr-specific constructor options.
- Do not change `WorkerHandle.last_inbound_sequence`, `seen_inbound_message_ids`, `_validate_inbound_message()`, IPC message validation, or Worker input sequencing here.
- Stage 1F must preserve the stderr task, decoder, reporter, cleanup, and tests introduced by this plan.

### Task 1: Centralize redaction and known-secret registration

**Files:**
- Create: `backend/src/agent_platform/infrastructure/redaction.py`
- Modify: `backend/src/agent_platform/infrastructure/logging/configure.py`
- Modify: `backend/src/agent_platform/interfaces/api/errors.py`
- Create: `backend/tests/unit/test_redaction.py`
- Modify: `backend/tests/unit/test_log_redaction.py`
- Modify: `backend/tests/contract/test_system_api.py`

- [ ] **Step 1: Implement the shared registry and sanitizer**

Use a `Counter[str]` protected by `threading.RLock`; registrations are reference-counted and `SecretRegistration.close()` is idempotent. Replace longer values first so overlapping tokens cannot partially survive.

`register_known_secret()` rejects empty or whitespace-only values before mutating the registry. It stores the exact non-empty value because surrounding whitespace may itself be part of a credential.

```python
SENSITIVE_KEYS: Final[frozenset[str]] = frozenset(
    {"api_key", "authorization", "credential", "password", "secret", "session_token", "token"}
)

def redact_text(value: str) -> str:
    with _LOCK:
        secrets = sorted(_KNOWN_SECRETS, key=len, reverse=True)
    for secret in secrets:
        value = value.replace(secret, "***")
    return value

def _sanitize(value: object, *, key: str | None = None) -> object:
    if key is not None and key.lower() in SENSITIVE_KEYS:
        return "***"
    if isinstance(value, str):
        return redact_text(value)
    if value is None or type(value) in {bool, int}:
        return value
    if type(value) is float:
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return sanitize_mapping(value)
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize(item) for item in value)
    return None
```

`configure.redact_secrets()` delegates to `sanitize_mapping()`. `interfaces/api/errors.py` removes `SENSITIVE_DETAIL_KEYS`, `_sanitize_detail_value()`, and its local recursion, then calls the same sanitizer.

- [ ] **Step 2: Add focused tests after implementation**

```python
def test_registered_secret_is_removed_from_embedded_text() -> None:
    registration = register_known_secret("session-secret")
    try:
        value = redact_text("Bearer session-secret https://x/?token=session-secret")
    finally:
        registration.close()
    assert value == "Bearer *** https://x/?token=***"

def test_registration_is_reference_counted() -> None:
    first = register_known_secret("shared-secret")
    second = register_known_secret("shared-secret")
    first.close()
    assert redact_text("shared-secret") == "***"
    second.close()
    assert redact_text("shared-secret") == "shared-secret"

@pytest.mark.parametrize("value", ["", "   "])
def test_known_secret_registration_rejects_empty_values(value: str) -> None:
    with pytest.raises(ValueError, match="known secret must not be empty"):
        register_known_secret(value)
```

Retain the existing nested-key, tuple, DomainError, and unhandled-request assertions; add an exception-text log containing a registered value and assert neither stderr nor JSONL contains it.

- [ ] **Step 3: Run focused verification and commit**

```powershell
cd D:\AgentProgram\.worktrees\backend-stage1\backend
uv run pytest tests/unit/test_redaction.py tests/unit/test_log_redaction.py tests/contract/test_system_api.py -q
uv run ruff check src tests/unit/test_redaction.py tests/unit/test_log_redaction.py tests/contract/test_system_api.py
uv run mypy src
git -C .. add backend/src/agent_platform/infrastructure/redaction.py backend/src/agent_platform/infrastructure/logging/configure.py backend/src/agent_platform/interfaces/api/errors.py backend/tests/unit/test_redaction.py backend/tests/unit/test_log_redaction.py backend/tests/contract/test_system_api.py
git -C .. commit -m "refactor: centralize diagnostic redaction"
```

### Task 2: Add bounded, non-blocking, safely rotating JSONL logging

**Files:**
- Modify: `backend/src/agent_platform/config/settings.py`
- Create: `backend/src/agent_platform/infrastructure/logging/files.py`
- Modify: `backend/src/agent_platform/infrastructure/logging/configure.py`
- Modify: `backend/src/agent_platform/main.py`
- Modify: `backend/tests/unit/test_settings.py`
- Modify: `backend/tests/unit/test_log_redaction.py`
- Create: `backend/tests/process/test_logging_runtime.py`
- Create: `backend/tests/process/test_uvicorn_logging.py`

- [ ] **Step 1: Implement bounded settings**

```python
log_file_max_bytes: int = Field(
    default=10 * 1024 * 1024,
    ge=64 * 1024,
    le=1024 * 1024 * 1024,
)
log_record_max_bytes: int = Field(default=32 * 1024, ge=1024, le=64 * 1024)
log_file_retained_count: int = Field(default=5, ge=1, le=50)
log_file_retention_days: int = Field(default=30, ge=1, le=3650)
log_queue_capacity: int = Field(default=4096, ge=64, le=65_536)
log_shutdown_drain_seconds: float = Field(default=1.0, ge=0.05, le=10.0)

@property
def log_file_retention_age(self) -> timedelta:
    return timedelta(days=self.log_file_retention_days)

@property
def log_shutdown_drain_timeout(self) -> timedelta:
    return timedelta(seconds=self.log_shutdown_drain_seconds)
```

The final UTF-8 JSONL line, including its trailing newline, must never exceed `log_record_max_bytes`. Because `log_record_max_bytes` is at most the minimum supported rotating-file size, one record cannot bypass the rotation boundary.

- [ ] **Step 2: Implement safe rotation and retention**

Build a `SafeRotatingFileHandler` compatible with `logging.handlers.RotatingFileHandler`, using `backend.jsonl`, UTF-8, `delay=True`, and an overridden `_open()` and `doRollover()`. Path-name validation alone is insufficient. Before opening anything, `log_root` must exist as a real directory and `lstat()` must reject a symlink or Windows reparse point. Opening the active file must use no-follow/handle semantics, verify from `fstat()` that the opened object is a regular file, and prove the opened handle still identifies `log_root/backend.jsonl`. On Windows, use `FILE_FLAG_OPEN_REPARSE_POINT`, reject `FILE_ATTRIBUTE_REPARSE_POINT`, and verify the final path obtained from the handle remains under the verified root. Never fall back to a normal path-following `open()` after a safety check fails.

Before every rollover, revalidate the open active-file handle, the pathname now occupying `backend.jsonl`, and every numbered source and destination. Reject symlinks, reparse points, non-regular files, identity changes, and pre-existing unsafe destinations; never overwrite through a link and never continue a partial rollover after validation fails. Publish each rename only within the verified root, reopen the active file through the same safe-open path, then call `prune_stale_log_files()`. The prune function accepts only `backend.jsonl.<positive integer>`, uses `lstat()`, rejects symlinks and Windows reparse points, verifies `candidate.resolve().parent == log_root.resolve()`, never opens a candidate, and never deletes `backend.jsonl`.

```python
_ROTATED_LOG_NAME = re.compile(r"backend\.jsonl\.[1-9][0-9]*\Z")

def prune_stale_log_files(... ) -> None:
    cutoff = (now or datetime.now(UTC)) - retention_age
    resolved_root = log_root.resolve(strict=True)
    for candidate in log_root.iterdir():
        if _ROTATED_LOG_NAME.fullmatch(candidate.name) is None:
            continue
        metadata = candidate.lstat()
        if _is_link_or_reparse(candidate, metadata):
            continue
        if candidate.resolve(strict=True).parent != resolved_root:
            continue
        if datetime.fromtimestamp(metadata.st_mtime, UTC) < cutoff:
            candidate.unlink()
```

- [ ] **Step 3: Enforce the final UTF-8 record limit**

Add `structlog.stdlib.add_logger_name` so every record contains `logger`; keep UTC `timestamp`, `level`, and `event`. The queue handler must immediately reduce stdlib or structlog input to JSON-safe primitives, redact registered secrets, and render the final immutable UTF-8 JSON line before enqueueing it. It may format only a string message with already-sanitized primitive/mapping/tuple arguments; it never invokes `str()`/`repr()` on an arbitrary object, never retains `exc_info`/tracebacks, and represents an exception only by its safe type name. Redaction and safe recursive conversion run before any length or digest calculation. A bounded renderer first replaces an individual sanitized string that cannot fit the record budget with a payload-free marker containing `truncated=true`, its sanitized UTF-8 byte length, and SHA-256. It then renders the complete JSON object. If aggregate nesting or many smaller fields still exceed the limit, replace the whole event with a minimal valid record that retains `timestamp`, `level`, and `logger`, sets `event="log_record_truncated"`, and records the sanitized original serialization's UTF-8 byte length and SHA-256.

The renderer must budget the handler's trailing newline and assert that the final encoded line is at most `max_record_bytes`; it must never split UTF-8, emit partial JSON, hash a pre-redaction value, or let message interpolation, exception text, a stdlib `extra` value, or a structlog event bypass the same bound. The queue contains only final `bytes` records and a private control sentinel, so closing the known-secret registration after a timed-out logging drain cannot make a later writer leak queued secrets.

- [ ] **Step 4: Put all sink I/O behind one bounded writer thread**

Attach exactly one custom bounded queue handler to the root logger. Its caller-side path performs only the bounded sanitizer/renderer from Step 3 and `put_nowait()`; it never flushes, opens, rotates, or writes a sink. One dedicated daemon writer thread exclusively owns the stderr stream and safe rotating file handler and writes the same already-rendered bytes to both. Consequently, `WorkerStderrReporter` and every other logger call from the asyncio loop can perform bounded CPU/memory work but no disk/console I/O. The queue handler never enqueues a live `LogRecord` or user object.

When the queue is full, atomically count dropped records and return immediately. The writer emits one payload-free `logging_queue_overflow` record with only dropped-record count and window timing before the next accepted detail; overflow accounting must not retain any dropped `LogRecord`, message, argument, exception, or Worker bytes. `LoggingRuntime.close()` is idempotent: stop admission, request a drain, wait no longer than `shutdown_drain_timeout`, and close sinks only after writer ownership ends. If a sink remains blocked, close raises a sanitized `LoggingDrainTimeout` at the deadline rather than joining forever; the daemon writer owns eventual cleanup and caller threads never race-close its handlers. Because every queued line was already bounded and redacted, no later registry change can alter it. Stage 1G must treat a still-live logging writer as an ownership dependency and fail stop instead of releasing the data-root lock beneath it.

- [ ] **Step 5: Own Uvicorn logging from the first process record**

`prepare_uvicorn_logging(level)` validates the level, removes and closes every handler from the root plus `uvicorn`, `uvicorn.error`, `uvicorn.access`, and `uvicorn.asgi`, makes all Uvicorn loggers propagate, and installs one root `NullHandler` as a pre-lifespan suppression boundary. `main.run()` calls it before constructing/running the server and passes `log_config=None` to `uvicorn.run()`. This deliberately drops Uvicorn records emitted before application lifespan has registered the session secret and opened the validated log root; they must never fall back to Uvicorn's plaintext handlers. `configure_logging()` repeats the Uvicorn handler/propagation adoption defensively and replaces the bootstrap `NullHandler` with the bounded queue handler. `LoggingRuntime.close()` restores the safe `NullHandler`, so Uvicorn shutdown records emitted after lifespan cannot escape through a plaintext fallback.

Create `tests/process/test_uvicorn_logging.py` using the actual console entry point and a disposable data root. Start on a selected loopback port, wait for readiness, send both a normal authenticated request and a request target containing the registered session token, then terminate cleanly. Assert process stdout/stderr contain no Uvicorn plaintext startup/access/error line and no token; parse every `backend.jsonl` line; assert post-lifespan `uvicorn.error` and `uvicorn.access` records use the common JSON keys and record limit; and assert the token is absent/replaced. Add a startup-failure case before lifespan and prove it exits without a plaintext traceback or token. No test may replace Uvicorn with a mock for this gate.

- [ ] **Step 6: Add tests after implementation**

Cover settings bounds; one record appearing in both stderr and `backend.jsonl`; required record keys; rotation under a small byte limit; count retention; age pruning; no deletion of unrelated names; UTF-8 payloads; and idempotent, deadline-bounded `LoggingRuntime.close()`. Add hostile-path cases for a linked/reparse `log_root`, pre-created linked/reparse `backend.jsonl`, replacement of the active path after its handle is open, and linked/reparse rollover sources and targets. Each case must fail closed and prove an outside sentinel is unchanged. On Windows, exercise the real handle/reparse implementation; if the host cannot create a reparse point, the low-level attribute/final-handle-path checks remain mandatory and only the privilege-dependent construction case may skip.

Emit multi-megabyte stdlib messages, exception strings, `extra` values, and structlog strings. After close, parse every line, assert every encoded line including `\n` is within `log_record_max_bytes`, assert truncation metadata contains sanitized length/hash, and assert neither raw oversized content nor a registered secret appears. Inspect the blocked queue in a test-only path and prove it contains only bounded immutable bytes/control sentinels: no `LogRecord`, traceback, exception, raw argument object, oversized text, or registered secret survives enqueue. Close the secret registration while the sink remains blocked, release it, and prove later output is still redacted. In a subprocess, install an intentionally blocking sink, flood logs and Worker stderr while it is blocked, and prove IPC ping/shutdown and the asyncio heartbeat continue within their deadlines, the queue never exceeds its configured capacity, overflow uses one payload-free summary, and close respects its drain deadline. Release the sink and prove the writer exits and owns final handler cleanup.

```python
event = json.loads((tmp_path / "logs/backend.jsonl").read_text(encoding="utf-8"))
assert {"timestamp", "level", "logger", "event"} <= event.keys()
assert event["event"] == "durable_probe"
```

- [ ] **Step 7: Run focused verification and commit**

```powershell
uv run pytest tests/unit/test_settings.py tests/unit/test_log_redaction.py tests/process/test_logging_runtime.py tests/process/test_uvicorn_logging.py -q
uv run ruff format --check src tests/unit/test_settings.py tests/unit/test_log_redaction.py tests/process/test_logging_runtime.py tests/process/test_uvicorn_logging.py
uv run ruff check src tests/unit/test_settings.py tests/unit/test_log_redaction.py tests/process/test_logging_runtime.py tests/process/test_uvicorn_logging.py
uv run mypy src
git -C .. add backend/src/agent_platform/config/settings.py backend/src/agent_platform/infrastructure/logging backend/src/agent_platform/main.py backend/tests/unit/test_settings.py backend/tests/unit/test_log_redaction.py backend/tests/process/test_logging_runtime.py backend/tests/process/test_uvicorn_logging.py
git -C .. commit -m "feat: persist rotating backend logs"
```

### Task 3: Build bounded Worker stderr evidence

**Files:**
- Create: `backend/src/agent_platform/infrastructure/workers/stderr.py`
- Create: `backend/tests/unit/test_worker_stderr.py`

- [ ] **Step 1: Implement evidence types and approved grammar**

```python
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
```

Accept only `worker bootstrap error`, `worker argument error`, `worker protocol error: <PythonIdentifier>`, and `worker internal error: <PythonIdentifier>` with an exception-type maximum of 64 ASCII characters. All other content becomes `OpaqueWorkerStderr`.

- [ ] **Step 2: Implement bounded assembly and reporting**

`WorkerStderrDecoder(max_line_bytes=4096)` hashes every byte while retaining at most 4096 bytes for grammar matching. `feed()` finalizes on LF and strips one preceding CR; `finish()` finalizes an unterminated line. `WorkerStderrReporter(max_records_per_window=32, window_seconds=1.0)` submits at most 32 detail records per window and then one payload-free summary containing suppressed line/byte counts. Its clock is injectable for deterministic tests. The reporter never receives or calls a file/stderr handler: production submission is a normal bound-logger call that reaches the global bounded queue from Task 2, while unit tests inject an in-memory callable.

- [ ] **Step 3: Add tests after implementation**

Test chunk boundaries, CRLF, invalid UTF-8, a 2 MiB unterminated line, digest accuracy, no raw unknown bytes in `repr()` or event mappings, safe grammar parsing, suppression summaries, and fixed retained-buffer size.

```python
evidence = decoder.finish()[0]
assert isinstance(evidence, OpaqueWorkerStderr)
assert evidence.byte_count == len(raw)
assert evidence.sha256 == hashlib.sha256(raw).hexdigest()
assert decoder.retained_byte_count == 0
```

- [ ] **Step 4: Run focused verification and commit**

```powershell
uv run pytest tests/unit/test_worker_stderr.py -q
uv run ruff check src tests/unit/test_worker_stderr.py
uv run mypy src
git -C .. add backend/src/agent_platform/infrastructure/workers/stderr.py backend/tests/unit/test_worker_stderr.py
git -C .. commit -m "feat: bound worker stderr evidence"
```

### Task 4: Integrate stderr evidence without blocking IPC

**Files:**
- Modify: `backend/src/agent_platform/infrastructure/workers/supervisor.py`
- Modify: `backend/tests/process/test_worker_supervisor.py`
- Modify: `backend/tests/fixtures/stderr_flood_worker.py`

- [ ] **Step 1: Replace discard-only drain with decoder/reporter pipeline**

Create a module logger with `structlog.get_logger(__name__)`. `_drain_stderr()` reads 16 KiB chunks, passes evidence to the reporter, and flushes an incomplete line/summary at EOF. Cancellation remains re-raised; all other reader failures emit only `worker_stderr_reader_failed` plus `exception_type`. Every reporter submission goes through the bounded queue handler and therefore does no synchronous formatting, file open, rotation, flush, or sink write on the asyncio event-loop thread.

```python
async def _drain_stderr(self, handle: WorkerHandle) -> None:
    reader = handle.process.stderr
    if reader is None:
        return
    decoder = WorkerStderrDecoder()
    reporter = WorkerStderrReporter(
        logger.bind(source="worker", worker_id=handle.worker_id, project_id=handle.project_id)
    )
    try:
        while chunk := await reader.read(16 * 1024):
            reporter.emit_all(decoder.feed(chunk))
        reporter.emit_all(decoder.finish())
    except asyncio.CancelledError:
        raise
    except Exception as error:
        reporter.reader_failed(type(error).__name__)
    finally:
        reporter.flush_summary()
```

- [ ] **Step 2: Add process tests after implementation**

Keep the existing 2 MiB flood ping/shutdown test. Configure a small file logger, run the fixture, close logging, parse every JSONL line, and assert the flood bytes never appear while a SHA-256/byte-count record does. Add a safe first-party diagnostic case and assert its structured category, worker ID, and project ID. Repeat the flood with the writer's sink intentionally blocked: ping, heartbeat, shutdown initiation, decoder retained-byte bound, and queue-capacity bound must still pass. After releasing the sink, assert one payload-free overflow summary, bounded shutdown drain, and writer-thread cleanup. This cross-check complements `tests/process/test_logging_runtime.py` and specifically proves Worker stderr cannot block IPC.

- [ ] **Step 3: Run focused verification and commit**

```powershell
uv run pytest tests/unit/test_worker_stderr.py tests/process/test_worker_supervisor.py -k "stderr or flood" -q
uv run ruff check src tests/unit/test_worker_stderr.py tests/process/test_worker_supervisor.py tests/fixtures/stderr_flood_worker.py
uv run mypy src
git -C .. add backend/src/agent_platform/infrastructure/workers backend/tests/unit/test_worker_stderr.py backend/tests/process/test_worker_supervisor.py backend/tests/fixtures/stderr_flood_worker.py
git -C .. commit -m "feat: persist safe worker diagnostics"
```

### Task 5: Own logging and secret registration in lifespan

**Files:**
- Modify: `backend/src/agent_platform/bootstrap/lifespan.py`
- Modify: `backend/tests/integration/test_application_lifespan.py`
- Modify: `backend/README.md`

- [ ] **Step 1: Integrate startup and cleanup**

Immediately after `ensure_directories()`, register `settings.session_token`, configure logging with the validated settings, and retain both resources locally. For Stage 1E the shutdown order is Watchdog, Workers, Database, Logging, SecretRegistration. Every cleanup runs; the first error stays primary and later errors add only `_CLEANUP_FAILURE_NOTE`. Add `logging_runtime` to app state only while lifespan is active.

```python
secret_registration = register_known_secret(settings.session_token)
logging_runtime = configure_logging(
    settings.log_root,
    settings.log_level,
    max_bytes=settings.log_file_max_bytes,
    max_record_bytes=settings.log_record_max_bytes,
    retained_file_count=settings.log_file_retained_count,
    retention_age=settings.log_file_retention_age,
    queue_capacity=settings.log_queue_capacity,
    shutdown_drain_timeout=settings.log_shutdown_drain_timeout,
)
```

`logging_runtime.close()` and `secret_registration.close()` are synchronous but each receives its own `try/except BaseException` cleanup slot. Stage 1G will place the instance lock before logging without changing these interfaces.

- [ ] **Step 2: Update lifecycle tests after implementation**

Extend order assertions to include `register_secret`, `configure_logging`, `close_logging`, and `unregister_secret`. Test configure failure, database failure, ordinary logging-close failure after database failure, `LoggingDrainTimeout` with an already-redacted queued record, repeated cancellation, and absence of the raw session token from stderr/JSONL/exception notes. Stage 1E may unregister after a drain timeout because no raw record/object remains queued; Stage 1G later adds the stricter instance-lock fail-stop dependency.

- [ ] **Step 3: Document runtime settings**

Document `AGENT_PLATFORM_LOG_FILE_MAX_BYTES`, `AGENT_PLATFORM_LOG_RECORD_MAX_BYTES`, `AGENT_PLATFORM_LOG_FILE_RETAINED_COUNT`, `AGENT_PLATFORM_LOG_FILE_RETENTION_DAYS`, `AGENT_PLATFORM_LOG_QUEUE_CAPACITY`, and `AGENT_PLATFORM_LOG_SHUTDOWN_DRAIN_SECONDS`, plus `logs/backend.jsonl`, pre-lifespan Uvicorn suppression, unified Uvicorn JSON logging after startup, and the guarantee that unknown Worker stderr is stored only as length/hash/flags.

- [ ] **Step 4: Run Stage 1E gate and commit**

```powershell
uv run pytest tests/unit/test_redaction.py tests/unit/test_log_redaction.py tests/unit/test_worker_stderr.py tests/process/test_logging_runtime.py tests/process/test_uvicorn_logging.py tests/process/test_worker_supervisor.py tests/integration/test_application_lifespan.py tests/contract/test_system_api.py -q
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
git -C .. add backend/src backend/tests backend/README.md docs/backend/BACKEND-STAGE1E-RUNTIME-DIAGNOSTICS-v1.md
git -C .. commit -m "test: verify runtime diagnostics"
```

Expected full-gate result: all tests pass; `backend.jsonl` is bounded and UTF-8 JSONL; no registered session token or raw unknown Worker stderr appears in output.
