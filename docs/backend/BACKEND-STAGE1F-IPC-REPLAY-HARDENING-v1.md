# Backend Stage 1F IPC Replay Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce strict positive consecutive IPC sequences and bounded recent message-ID replay detection in both Backend and Worker directions without changing IPC v1.

**Architecture:** A shared `ReplayWindow` owns sequence and message-ID acceptance. It stores only fixed-size SHA-256 message-ID digests in a fixed-capacity deque plus set, evicting from both collections together; raw attacker-controlled IDs are never retained. The wire contract also caps message-ID length. The Backend stores one window per `WorkerHandle`; the Worker stores one window per process lifetime, which remains the IPC session boundary.

**Tech Stack:** Python 3.12, asyncio, collections.deque, Pydantic Settings/models, pytest, Ruff, mypy.

**Process override:** The user explicitly requested implementation-first testing for Stage 1E–1I. Implement each approved behavior before adding its focused tests; all tests and quality gates remain mandatory.

**Command convention:** Every command block runs from `D:\AgentProgram\.worktrees\backend-stage1\backend`. Git commands use `git -C ..` so repository-root paths remain exact.

---

## File Map and Responsibilities

```text
backend/src/agent_platform/
|- interfaces/ipc/
|  |- replay.py       # shared capacity validation and ReplayWindow
|  `- messages.py     # wire-level positive StrictInt sequence and bounded message ID
|- config/settings.py # configured bounded replay-window capacity
|- infrastructure/workers/supervisor.py
|  `- Backend inbound ReplayWindow and Worker capacity propagation
|- bootstrap/lifespan.py
|  `- pass validated capacity to WorkerSupervisor
`- workers/main.py
   `- Worker inbound ReplayWindow and hidden capacity argument

backend/tests/
|- unit/test_ipc_replay.py
|- unit/test_ipc_framing.py
|- unit/test_settings.py
|- process/test_worker_supervisor.py
|- process/test_worker_protocol.py
|- fixtures/invalid_inbound_worker.py
`- integration/test_application_lifespan.py
```

## Frozen Shared Interface

```python
MIN_REPLAY_WINDOW_CAPACITY: Final[int] = 64
DEFAULT_REPLAY_WINDOW_CAPACITY: Final[int] = 4096
MAX_REPLAY_WINDOW_CAPACITY: Final[int] = 65_536
MAX_IPC_MESSAGE_ID_LENGTH: Final[int] = 128

class IpcReplayError(ValueError): ...

@dataclass(slots=True)
class ReplayWindow:
    capacity: int = DEFAULT_REPLAY_WINDOW_CAPACITY
    @property
    def last_sequence(self) -> int: ...
    @property
    def remembered_message_count(self) -> int: ...
    def accept(self, *, sequence: int, message_id: str) -> None: ...

def validate_replay_window_capacity(value: object) -> int: ...
def parse_replay_window_capacity_arg(value: str) -> int: ...
```

## Explicit Continuity from Stage 1E

- Preserve `WorkerSupervisor._stderr_task`, `WorkerStderrDecoder`, `WorkerStderrReporter`, `_drain_stderr()`, structured logger bindings, and stderr cleanup exactly as delivered by Stage 1E.
- In `WorkerHandle`, replace only the unbounded replay fields; do not recreate the entire dataclass from an older revision.
- Keep the Stage 1E logging runtime and secret-registration arguments when editing lifespan constructor calls and tests.
- No Worker restart, new message field, protocol-version bump, acknowledgement change, or cross-process replay persistence.

### Task 1: Implement the shared bounded ReplayWindow

**Files:**
- Create: `backend/src/agent_platform/interfaces/ipc/replay.py`
- Create: `backend/tests/unit/test_ipc_replay.py`

- [ ] **Step 1: Implement capacity validation and acceptance**

```python
def validate_replay_window_capacity(value: object) -> int:
    if type(value) is not int:
        raise ValueError("replay-window capacity must be an integer")
    if not MIN_REPLAY_WINDOW_CAPACITY <= value <= MAX_REPLAY_WINDOW_CAPACITY:
        raise ValueError("replay-window capacity is outside the supported range")
    return value

def parse_replay_window_capacity_arg(value: str) -> int:
    if re.fullmatch(r"[1-9][0-9]*", value) is None:
        raise argparse.ArgumentTypeError("must be a supported replay-window capacity")
    try:
        return validate_replay_window_capacity(int(value, 10))
    except ValueError:
        raise argparse.ArgumentTypeError(
            "must be a supported replay-window capacity"
        ) from None

@dataclass(slots=True)
class ReplayWindow:
    capacity: int = DEFAULT_REPLAY_WINDOW_CAPACITY
    _last_sequence: int = field(default=0, init=False)
    _message_digests: deque[bytes] = field(default_factory=deque, init=False, repr=False)
    _message_digest_set: set[bytes] = field(default_factory=set, init=False, repr=False)

    def __post_init__(self) -> None:
        self.capacity = validate_replay_window_capacity(self.capacity)

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
```

Expose read-only properties for the last sequence and retained count; never expose mutable collections or raw IDs. Digest equality is used only as a fail-closed replay signal: a theoretical collision may reject a valid message but can never accept a replay.

- [ ] **Step 2: Add tests after implementation**

Test default/min/max capacities; reject bool, float, string, below-minimum, and above-maximum capacities; test the CLI adapter accepts canonical decimal min/max strings while rejecting whitespace, signs, leading zeroes, non-decimal text, and out-of-range values without echoing input; reject zero, negative, duplicate, skipped, and reversed sequences; reject empty and over-128-character IDs; reject a reused ID at the next valid sequence; process more than twice the capacity and prove both digest collections remain at capacity; prove an evicted ID may be reused with the next valid sequence.

```python
window = ReplayWindow(capacity=MIN_REPLAY_WINDOW_CAPACITY)
for sequence in range(1, 10_001):
    window.accept(sequence=sequence, message_id=f"msg-{sequence}")
assert window.last_sequence == 10_000
assert window.remembered_message_count == MIN_REPLAY_WINDOW_CAPACITY
```

Add a byte-pressure test using the maximum capacity and maximum-length multi-byte IDs. Inspect only the private collections inside the unit test and prove every retained item is exactly a 32-byte digest, the deque and set reference the same `capacity` digest objects, no raw ID is present, and total retained attacker-derived payload is at most `capacity * 32` bytes before normal Python container/reference overhead. Also pass a near-frame-sized direct ID and prove it is rejected before retention.

- [ ] **Step 3: Run focused verification and commit**

```powershell
cd D:\AgentProgram\.worktrees\backend-stage1\backend
uv run pytest tests/unit/test_ipc_replay.py -q
uv run ruff check src tests/unit/test_ipc_replay.py
uv run mypy src
git -C .. add backend/src/agent_platform/interfaces/ipc/replay.py backend/tests/unit/test_ipc_replay.py
git -C .. commit -m "feat: add bounded ipc replay window"
```

### Task 2: Make the IPC wire sequence strictly positive

**Files:**
- Modify: `backend/src/agent_platform/interfaces/ipc/messages.py`
- Modify: `backend/tests/unit/test_ipc_framing.py`

- [ ] **Step 1: Tighten the model**

```python
MessageId = Annotated[str, Field(min_length=1, max_length=MAX_IPC_MESSAGE_ID_LENGTH)]

message_id: MessageId
sequence: StrictInt = Field(ge=1)
```

Import the shared length constant from `interfaces.ipc.replay`. Keep `ConfigDict(strict=True)` and the existing protocol-version validator. This rejects empty/overlong message IDs plus `0`, negative integers, booleans, floats, and strings before either runtime sees a message. Update the decoder compaction fixture from `range(100)` to `range(1, 101)`; no production sender emits sequence zero.

- [ ] **Step 2: Add tests after implementation**

Rename the negative-only test to a non-positive parameterized test using `[0, -1]`. Keep Python/JSON strict-scalar cases and add raw zero-sequence plus overlong-message-ID frame assertions that `FrameDecoder.feed()` raises `FramingError` without including the body or rejected ID.

- [ ] **Step 3: Run focused verification and commit**

```powershell
uv run pytest tests/unit/test_ipc_framing.py -q
uv run ruff check src tests/unit/test_ipc_framing.py
uv run mypy src
git -C .. add backend/src/agent_platform/interfaces/ipc/messages.py backend/tests/unit/test_ipc_framing.py
git -C .. commit -m "fix: require positive ipc sequences"
```

### Task 3: Apply ReplayWindow to Backend inbound messages

**Files:**
- Modify: `backend/src/agent_platform/config/settings.py`
- Modify: `backend/src/agent_platform/infrastructure/workers/supervisor.py`
- Modify: `backend/src/agent_platform/bootstrap/lifespan.py`
- Modify: `backend/tests/unit/test_settings.py`
- Modify: `backend/tests/process/test_worker_supervisor.py`
- Modify: `backend/tests/fixtures/invalid_inbound_worker.py`
- Modify: `backend/tests/integration/test_application_lifespan.py`

- [ ] **Step 1: Add the validated setting and Supervisor parameter**

```python
worker_ipc_replay_window_capacity: int = Field(
    default=DEFAULT_REPLAY_WINDOW_CAPACITY,
    ge=MIN_REPLAY_WINDOW_CAPACITY,
    le=MAX_REPLAY_WINDOW_CAPACITY,
)
```

`WorkerSupervisor.__init__()` receives keyword-only `ipc_replay_window_capacity: int = DEFAULT_REPLAY_WINDOW_CAPACITY` and validates it with the shared function. Lifespan passes `settings.worker_ipc_replay_window_capacity` while retaining all Stage 1E arguments.

- [ ] **Step 2: Replace unbounded handle state**

```python
@dataclass
class WorkerHandle:
    # existing Stage 1E fields stay unchanged
    inbound_replay: ReplayWindow = field(default_factory=ReplayWindow, repr=False)
```

Delete `last_inbound_sequence` and `seen_inbound_message_ids`. When constructing a handle, pass `ReplayWindow(self._ipc_replay_window_capacity)`.

- [ ] **Step 3: Validate through the shared component**

Keep project and heartbeat schema checks, then atomically accept the sequence and ID. Translate `IpcReplayError` to the existing sanitized `FramingError`; never include sequence or message ID in the error.

```python
try:
    handle.inbound_replay.accept(
        sequence=message.sequence,
        message_id=message.message_id,
    )
except IpcReplayError:
    raise FramingError("worker message replay validation failed") from None
```

- [ ] **Step 4: Extend fixtures and add tests after implementation**

Keep current repeated/skipped tests. Add fixture modes for reversed sequence and same message ID with the next valid sequence so ID reuse is tested independently of sequence mismatch. Add a direct handle test that accepts `capacity * 3` valid messages and asserts `remembered_message_count == capacity`. Verify protocol failure still terminates the Worker, fails pending requests, drains stderr, and clears both registries.

- [ ] **Step 5: Run focused verification and commit**

```powershell
uv run pytest tests/unit/test_settings.py tests/process/test_worker_supervisor.py tests/integration/test_application_lifespan.py -k "replay or sequence or capacity or lifespan" -q
uv run ruff check src tests/unit/test_settings.py tests/process/test_worker_supervisor.py tests/fixtures/invalid_inbound_worker.py tests/integration/test_application_lifespan.py
uv run mypy src
git -C .. add backend/src/agent_platform/config/settings.py backend/src/agent_platform/infrastructure/workers/supervisor.py backend/src/agent_platform/bootstrap/lifespan.py backend/tests/unit/test_settings.py backend/tests/process/test_worker_supervisor.py backend/tests/fixtures/invalid_inbound_worker.py backend/tests/integration/test_application_lifespan.py
git -C .. commit -m "fix: bound backend ipc replay state"
```

### Task 4: Apply ReplayWindow to Worker inbound messages

**Files:**
- Modify: `backend/src/agent_platform/workers/main.py`
- Modify: `backend/src/agent_platform/infrastructure/workers/supervisor.py`
- Modify: `backend/tests/process/test_worker_protocol.py`

- [ ] **Step 1: Add a hidden validated Worker capacity argument**

Add `--ipc-replay-window-capacity` with `parse_replay_window_capacity_arg` and default 4096. Do not pass `validate_replay_window_capacity` directly to argparse: both argparse input and Supervisor-launched arguments are strings, while that strict validator intentionally rejects strings. `WorkerSupervisor.start()` appends this argument only when launching `agent_platform.workers.main`; test fixture modules retain their existing command lines. This is a process-launch option, not an IPC v1 field.

```python
if worker_module == "agent_platform.workers.main":
    target_arguments += (
        "--ipc-replay-window-capacity",
        str(self._ipc_replay_window_capacity),
    )
```

- [ ] **Step 2: Replace Worker input sequence state**

`_WorkerProtocol.__init__()` receives `replay_window_capacity`, creates `self._inbound_replay`, and removes `_last_input_sequence`. `_handle_message()` calls `accept()` before semantic handling; `IpcReplayError` becomes `_WorkerInputProtocolError` with no chained raw data. Heartbeats report `self._inbound_replay.last_sequence`.

```python
try:
    self._inbound_replay.accept(
        sequence=message.sequence,
        message_id=message.message_id,
    )
except IpcReplayError:
    raise _WorkerInputProtocolError from None
```

- [ ] **Step 3: Add process tests after implementation**

Send duplicate, skipped, reversed, same-ID/next-sequence, and overlong-ID frames to the Worker and assert exit code 2, framed stdout contains no response to the invalid message, stderr contains only the existing safe protocol category, and raw IDs/payloads are absent. Keep interleaved heartbeat/command monotonicity and clean shutdown tests. Launch the real Worker through `WorkerSupervisor` to prove the string capacity argument is accepted in production at min/default/max, then reject out-of-range, signed, whitespace-padded, leading-zero, and non-decimal CLI values without echoing submitted input.

- [ ] **Step 4: Run focused verification and commit**

```powershell
uv run pytest tests/unit/test_ipc_replay.py tests/unit/test_ipc_framing.py tests/process/test_worker_protocol.py tests/process/test_worker_supervisor.py -q
uv run ruff check src tests/unit/test_ipc_replay.py tests/unit/test_ipc_framing.py tests/process/test_worker_protocol.py tests/process/test_worker_supervisor.py
uv run mypy src
git -C .. add backend/src/agent_platform/workers/main.py backend/src/agent_platform/infrastructure/workers/supervisor.py backend/tests/process/test_worker_protocol.py backend/tests/process/test_worker_supervisor.py
git -C .. commit -m "fix: reject worker ipc replay"
```

### Task 5: Complete Stage 1F regression and boundedness gate

**Files:**
- Modify only if verification finds a compatibility defect: files listed in Tasks 1-4
- Modify: `backend/README.md`

- [ ] **Step 1: Document the configured boundary**

Document `AGENT_PLATFORM_WORKER_IPC_REPLAY_WINDOW_CAPACITY`, default 4096, supported range 64–65536, the 128-character wire message-ID bound, digest-only replay retention, per-process lifetime, strict consecutive sequence requirement, and the unchanged IPC protocol version 1.

- [ ] **Step 2: Search for stale unbounded state and wire drift**

```powershell
$forbidden = & rg -n "seen_inbound_message_ids|last_inbound_sequence|sequence: StrictInt = Field\(ge=0\)" src tests 2>&1
$status = $LASTEXITCODE
if ($status -eq 0) {
    $forbidden
    throw 'Stale unbounded IPC replay state remains.'
}
if ($status -ne 1) {
    $forbidden
    throw "rg failed with exit code $status."
}

$protocol = & rg -n 'protocol_version: Literal\[1\]|Protocol-Version: 1' src/agent_platform/interfaces/ipc 2>&1
if ($LASTEXITCODE -ne 0) {
    $protocol
    throw 'IPC protocol version 1 marker is missing.'
}
$protocol
```

Expected: first search has no production matches; protocol version remains 1.

- [ ] **Step 3: Run complete gate**

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

- [ ] **Step 4: Commit compatibility-only corrections**

```powershell
git -C .. add backend/src backend/tests backend/README.md docs/backend/BACKEND-STAGE1F-IPC-REPLAY-HARDENING-v1.md
git -C .. commit -m "test: verify ipc replay hardening"
```

Expected final result: both directions fail closed on non-positive, duplicate, skipped, reversed, non-integer, overlong, or near-term reused-ID input; a long-running session retains at most the configured number of fixed-size message-ID digests; all Stage 1E stderr/logging behavior still passes.
