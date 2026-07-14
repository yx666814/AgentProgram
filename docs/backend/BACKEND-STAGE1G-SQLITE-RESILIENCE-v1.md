# Backend Stage 1G SQLite Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Backend the sole cross-process owner of its SQLite data root and add bounded integrity checks, verified online backups, WAL maintenance, safe retention, size warnings, and failure-safe lifecycle cleanup.

**Architecture:** A shared cross-platform advisory-lock component protects both Backend startup and online Alembic migrations. Dedicated synchronous SQLite helpers perform integrity, checkpoint, backup, verification, retention, and restore work off the event loop through cooperatively cancellable, deadline-aware jobs that are always joined before the instance lock can be released; a lifecycle-owned maintenance service schedules them and publishes a small health snapshot. The Stage 1E logging writer is also an ownership dependency: if it cannot stop by its deadline, the Backend fails stop instead of releasing the data-root lock beneath a live file writer. The implementation preserves the existing first-error/sanitized-secondary-error cleanup rule for recoverable failures and does not edit the immutable foundation migration.

**Tech Stack:** Python 3.12, `msvcrt` on Windows, `fcntl` on POSIX, stdlib `sqlite3` Backup API, asyncio, SQLAlchemy/aiosqlite, Alembic, FastAPI, Pydantic Settings, pytest.

**Process override:** The user explicitly requested implementation-first testing for Stage 1E–1I. Implement each approved behavior before adding its focused tests; all tests and quality gates remain mandatory.

---

## Fixed boundaries and file map

- Product Git behavior remains out of scope.
- Never copy, delete, rename, or retain-manage `agent.db-wal` or `agent.db-shm` directly.
- `backend/migrations/versions/0001_foundation.py` remains byte-for-byte unchanged.
- Offline Alembic rendering remains filesystem side-effect free.
- Validate `data_root`, `runtime_root`, `backup_root`, destination parents, and every existing ancestor component before use; symbolic links, mount/junction substitutions, and Windows reparse points fail closed. Revalidate the final path from each opened handle before mutating it so a path-check/open TOCTOU cannot redirect work outside the owned root.
- Only application-owned names under validated `log_root`, `backup_root`, and `runtime_root` are eligible for maintenance. A bounded inventory that is not complete performs no deletion.
- Backend startup and online Alembic use `runtime_root/backend.lock`; metadata is diagnostic only and never proves ownership.
- The backup database is published and directory-synced before its manifest; the manifest is published and directory-synced last and is the sole commit marker.
- A manifest revision must exactly equal the revision embedded in its backup database. `null` is accepted only for a valid pre-Alembic database, and a non-null revision may be any known revision in the Alembic history graph, not only the current head.
- EventLog and unresolved Outbox/dead-letter data are never removed in Stage 1G.

Before Task 1, freeze the implementation range once from the repository root so the final immutable-file check spans every Stage 1G commit as well as the working tree:

```powershell
$repo = 'D:\AgentProgram\.worktrees\backend-stage1'
git -C $repo update-ref refs/codex/stage1g-base HEAD
```

**Create:**

- `backend/src/agent_platform/infrastructure/database/filesystem_safety.py` — owned-root validation, opened-handle final-path checks, no-follow/reparse checks, and durable directory sync.
- `backend/src/agent_platform/infrastructure/database/instance_lock.py` — OS advisory lock and stable unavailable error.
- `backend/src/agent_platform/infrastructure/database/integrity.py` — bounded `quick_check`/`integrity_check` and WAL checkpoint primitives.
- `backend/src/agent_platform/infrastructure/database/backup.py` — online backup, manifest, verification, restore, orphan cleanup, and retention.
- `backend/src/agent_platform/infrastructure/database/maintenance.py` — scheduled maintenance and health state.
- `backend/tests/unit/test_database_instance_lock.py`
- `backend/tests/unit/test_database_integrity.py`
- `backend/tests/integration/test_database_backup.py`
- `backend/tests/integration/test_database_maintenance.py`

**Modify:**

- `backend/src/agent_platform/config/settings.py`
- `backend/src/agent_platform/bootstrap/lifespan.py`
- `backend/src/agent_platform/interfaces/api/routes/health.py`
- `backend/src/agent_platform/infrastructure/database/__init__.py`
- `backend/src/agent_platform/infrastructure/logging/files.py` — Stage 1G cross-stage hardening only: add a bounded inventory parameter to Stage 1E log pruning.
- `backend/migrations/env.py`
- `backend/tests/unit/test_settings.py`
- `backend/tests/unit/test_logging_files.py`
- `backend/tests/integration/test_application_lifespan.py`
- `backend/tests/process/test_logging_fail_stop.py`
- `backend/tests/integration/test_database_bootstrap.py`
- `backend/tests/migration/test_foundation_migration.py`

## Frozen public/internal interfaces

```python
# infrastructure/database/instance_lock.py
class InstanceLockUnavailableError(DomainError): ...

class ApplicationInstanceLock:
    def __init__(self, path: Path, *, data_root: Path) -> None: ...
    def acquire(self) -> None: ...
    def release(self) -> None: ...
    def __enter__(self) -> Self: ...
    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None: ...

# infrastructure/database/integrity.py
class IntegrityCheckMode(StrEnum):
    QUICK = "quick_check"
    FULL = "integrity_check"

class WalCheckpointMode(StrEnum):
    PASSIVE = "PASSIVE"
    TRUNCATE = "TRUNCATE"

@dataclass(frozen=True)
class IntegrityCheckResult:
    mode: IntegrityCheckMode
    ok: bool
    issue_count: int

@dataclass(frozen=True)
class WalCheckpointResult:
    busy: bool
    log_frames: int
    checkpointed_frames: int

async def check_database_integrity(path: Path, mode: IntegrityCheckMode, timeout_seconds: float) -> IntegrityCheckResult: ...
async def require_database_integrity(path: Path, mode: IntegrityCheckMode, timeout_seconds: float) -> None: ...
async def checkpoint_database(path: Path, mode: WalCheckpointMode, timeout_seconds: float) -> WalCheckpointResult: ...

# infrastructure/database/backup.py
BackupReason = Literal["scheduled", "pre_migration"]

@dataclass(frozen=True)
class BackupManifest:
    format_version: int
    database_filename: str
    schema_revision: str | None
    created_at: datetime
    byte_size: int
    sha256: str
    reason: BackupReason

@dataclass(frozen=True)
class VerifiedBackup:
    database_path: Path
    manifest_path: Path
    manifest: BackupManifest

def create_verified_backup(database_path: Path, backup_root: Path, *, reason: BackupReason, now: datetime | None = None) -> VerifiedBackup: ...
def verify_backup(manifest_path: Path) -> VerifiedBackup: ...
def restore_verified_backup(manifest_path: Path, destination_path: Path) -> None: ...
def prune_backup_root(backup_root: Path, *, retain_count: int, retention_age: timedelta, max_entries: int, now: datetime | None = None) -> None: ...

# infrastructure/database/maintenance.py
@dataclass(frozen=True)
class DatabaseHealthSnapshot:
    size_bytes: int
    size_warning: bool
    checkpoint_busy: bool
    integrity_ok: bool | None
    last_backup_at: datetime | None

class DatabaseMaintenance:
    def __init__(self, settings: Settings) -> None: ...
    async def run_forever(self) -> None: ...
    async def run_once(self, *, force_integrity: bool = False, force_backup: bool = False) -> None: ...
    async def stop(self) -> None: ...
    async def final_checkpoint(self) -> WalCheckpointResult: ...
    def snapshot(self) -> DatabaseHealthSnapshot: ...
```

### Task 1: Add bounded SQLite settings and health vocabulary

**Files:**

- Modify: `backend/src/agent_platform/config/settings.py`
- Modify: `backend/tests/unit/test_settings.py`

- [ ] **Step 1: Implement settings before tests**

Add these exact fields and property:

```python
database_operation_timeout_seconds: float = 30.0
database_maintenance_interval_seconds: float = 300.0
database_integrity_check_interval_seconds: float = 86_400.0
database_backup_interval_seconds: float = 86_400.0
database_backup_retention_count: int = Field(default=7, ge=1, le=365)
database_backup_retention_days: int = Field(default=30, ge=1, le=3_650)
database_maintenance_max_entries_per_run: int = Field(default=256, ge=1, le=10_000)
database_size_warning_bytes: int = Field(default=1_073_741_824, ge=1)

@property
def instance_lock_path(self) -> Path:
    return self.runtime_root / "backend.lock"
```

Extend the positive-finite validator to all four float settings. Add an `after` validator requiring `database_maintenance_interval_seconds` to be no greater than both the integrity and backup intervals.

- [ ] **Step 2: Add focused settings tests**

Cover exact defaults, `instance_lock_path`, non-finite/non-positive values, bounded integer fields, and the maintenance-interval relationship in `backend/tests/unit/test_settings.py`.

- [ ] **Step 3: Verify and commit**

```powershell
$repo = 'D:\AgentProgram\.worktrees\backend-stage1'
$backend = Join-Path $repo 'backend'
Push-Location $backend
try {
    uv run pytest tests/unit/test_settings.py -q
    uv run ruff check src/agent_platform/config/settings.py tests/unit/test_settings.py
} finally {
    Pop-Location
}
git -C $repo add -- backend/src/agent_platform/config/settings.py backend/tests/unit/test_settings.py
git -C $repo commit -m "feat: define sqlite resilience settings"
```

Expected: focused tests pass and Ruff reports no errors.

### Task 2: Implement one shared OS advisory lock for Backend and Alembic

**Files:**

- Create: `backend/src/agent_platform/infrastructure/database/filesystem_safety.py`
- Create: `backend/src/agent_platform/infrastructure/database/instance_lock.py`
- Create: `backend/tests/unit/test_database_instance_lock.py`
- Modify: `backend/migrations/env.py`
- Modify: `backend/tests/migration/test_foundation_migration.py`

- [ ] **Step 1: Implement owned-path validation and the lock**

Add shared internal helpers that validate the configured `data_root`, its `runtime_root`, and every existing ancestor from a stable absolute anchor. On POSIX, walk/open directory components with no-follow directory handles and open the leaf relative to the validated parent; on Windows, inspect each component with reparse-point-aware handles. Reject symlinks, junctions, mount-point substitutions, non-directory ancestors, and any path whose opened-handle final path is not the expected normalized path beneath the configured root. Use the final opened handle for subsequent `fstat`, writes, fsync, and rename decisions rather than re-opening a previously checked pathname. The helpers also provide a platform-specific durable parent-directory sync (`fsync` on a directory descriptor on POSIX; a directory handle plus `FlushFileBuffers` on Windows) and fail closed when validation or sync cannot be established.

Open `backend.lock` only through that helper in unbuffered binary append/update mode, ensure byte zero exists, and acquire non-blockingly. Windows must seek to byte zero and call `msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)`; POSIX must call `fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)`. Convert only lock-contention errors into:

```python
class InstanceLockUnavailableError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            code="backend.instance_unavailable",
            message="Backend data is already in use.",
            retryable=True,
            category=ErrorCategory.UNAVAILABLE,
        )
```

After ownership is proven, overwrite metadata with compact UTF-8 JSON containing only `pid`, Backend `version`, and UTC `acquired_at`; flush and `os.fsync`. `release()` is idempotent and never deletes the lock file. On Windows it must `seek(0)` immediately before `msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)`; on every platform the close is in `finally`, the stored handle is cleared even if unlock fails, and only a sanitized cleanup failure escapes. Never release the lock while a maintenance/backup/restore worker thread can still access the data root.

- [ ] **Step 2: Put online Alembic inside the same lock boundary**

Keep `run_migrations_offline()` unchanged. In `run_migrations_online()`, validate/create `data_root/runtime` component-by-component through the shared owned-path helper, then wrap engine creation, connection, migration, `_drop_empty_sqlite_version_table`, and engine disposal in:

```python
data_root = _data_root()
lock = ApplicationInstanceLock(
    data_root / "runtime" / "backend.lock",
    data_root=data_root,
)
with lock:
    connectable = engine_from_config(...)
    try:
        with connectable.connect() as connection:
            ...
    finally:
        connectable.dispose()
```

- [ ] **Step 3: Add real cross-process tests after implementation**

Tests must prove: first owner succeeds; a spawned second Python process receives only code `backend.instance_unavailable`; release permits reacquisition; metadata is not trusted; Windows exercises `msvcrt` rather than a PID existence check; Windows unlock seeks back to byte zero even after metadata writes and closes in `finally`; POSIX uses its advisory equivalent; data/runtime ancestor symlinks and Windows junction/reparse substitutions fail closed; an attacker swapping a checked path before open cannot redirect the opened handle outside `data_root`; opened-handle final-path mismatch fails closed; offline Alembic creates no runtime/data directories; concurrent Backend/Alembic ownership fails closed.

- [ ] **Step 4: Verify and commit**

```powershell
$repo = 'D:\AgentProgram\.worktrees\backend-stage1'
$backend = Join-Path $repo 'backend'
Push-Location $backend
try {
    uv run pytest tests/unit/test_database_instance_lock.py tests/migration/test_foundation_migration.py -q
    uv run ruff check src/agent_platform/infrastructure/database/filesystem_safety.py src/agent_platform/infrastructure/database/instance_lock.py migrations/env.py tests/unit/test_database_instance_lock.py tests/migration/test_foundation_migration.py
} finally {
    Pop-Location
}
git -C $repo add -- backend/src/agent_platform/infrastructure/database/filesystem_safety.py backend/src/agent_platform/infrastructure/database/instance_lock.py backend/migrations/env.py backend/tests/unit/test_database_instance_lock.py backend/tests/migration/test_foundation_migration.py
git -C $repo commit -m "feat: enforce single sqlite owner"
```

### Task 3: Add bounded integrity checks and WAL checkpoints

**Files:**

- Create: `backend/src/agent_platform/infrastructure/database/integrity.py`
- Create: `backend/tests/unit/test_database_integrity.py`
- Modify: `backend/tests/integration/test_database_bootstrap.py`

- [ ] **Step 1: Implement synchronous primitives and async wrappers**

Open a dedicated stdlib `sqlite3` connection with the configured timeout, install a progress handler that checks both a monotonic deadline and a `threading.Event` cancellation signal, and execute only enum-selected pragmas. Integrity succeeds only when the complete result is one row equal to `"ok"`. `require_database_integrity` raises a sanitized `DatabaseIntegrityError` with code `database.integrity_failed`; it must not include a path or SQLite diagnostic text.

Checkpoint with `PRAGMA wal_checkpoint(PASSIVE)` during maintenance and `PRAGMA wal_checkpoint(TRUNCATE)` at final shutdown. Return all three SQLite counters through `WalCheckpointResult`; `busy != 0` is reported, not hidden. Do not inspect or manipulate WAL/SHM paths.

Do not use a naked `wait_for(asyncio.to_thread(...))`: cancelling that await does not stop the underlying thread. Route every lifecycle-owned integrity, checkpoint, backup, verification, retention, and restore operation through one internal cooperative runner with this contract:

```python
control = DatabaseOperationControl(
    deadline=monotonic() + timeout_seconds,
    cancelled=threading.Event(),
)
worker = asyncio.create_task(asyncio.to_thread(sync_operation, control))
try:
    return await asyncio.wait_for(asyncio.shield(worker), timeout_seconds + 0.25)
except (TimeoutError, asyncio.CancelledError):
    control.cancelled.set()
    await _join_worker_preserving_cancellation(worker)
    raise
```

The synchronous SQLite progress/backup callbacks and every bounded scan loop check `control` and abort promptly. `_join_worker_preserving_cancellation()` retrieves the worker result/exception and cannot be bypassed by the shutdown cancellation it is servicing; repeated cancellation is remembered and re-raised only after the thread has exited. Never assume `Future.cancel()` terminated a thread and never leave a detached `to_thread` job. A non-interruptible OS call may delay the join, but safety wins: database disposal and instance-lock release wait for confirmed thread exit.

- [ ] **Step 2: Add tests after implementation**

Cover healthy quick/full checks, corrupted SQLite rejection without leaked path/message, cooperative deadline expiry, explicit task cancellation, proof that the worker has exited before the async wrapper returns/raises, PASSIVE/TRUNCATE counters, busy reporting with an active reader, and preservation of reader/writer WAL behavior.

- [ ] **Step 3: Verify and commit**

```powershell
$repo = 'D:\AgentProgram\.worktrees\backend-stage1'
$backend = Join-Path $repo 'backend'
Push-Location $backend
try {
    uv run pytest tests/unit/test_database_integrity.py tests/integration/test_database_bootstrap.py -q
    uv run mypy src/agent_platform/infrastructure/database/integrity.py
} finally {
    Pop-Location
}
git -C $repo add -- backend/src/agent_platform/infrastructure/database/integrity.py backend/tests/unit/test_database_integrity.py backend/tests/integration/test_database_bootstrap.py
git -C $repo commit -m "feat: add sqlite integrity and checkpoint primitives"
```

### Task 4: Implement committed online backups, verification, restore, and retention

**Files:**

- Create: `backend/src/agent_platform/infrastructure/database/backup.py`
- Create: `backend/tests/integration/test_database_backup.py`
- Modify: `backend/migrations/env.py`
- Modify: `backend/tests/migration/test_foundation_migration.py`

- [ ] **Step 1: Implement the committed backup format**

Recognize only `agent-backup-<UTC basic timestamp>-<32 lowercase hex>.sqlite3` and the exact `.manifest.json` sidecar. Validate `data_root`/`backup_root`, every ancestor, and opened-handle final paths with the shared filesystem-safety helpers. Use source and destination stdlib SQLite connections plus `source.backup(destination)`; direct file copy is forbidden. All SQLite backup progress callbacks and hashing loops observe the cooperative operation control.

Use exclusive, no-follow random temporary names in the same validated `backup_root` and this exact durability order:

1. Stream the SQLite backup into the database temp file, close SQLite handles, run `quick_check`, read its embedded Alembic revision, compute size/SHA-256, and fsync the database temp handle.
2. Write canonical compact/sorted JSON to the manifest temp file and fsync that file; temp files are never considered committed.
3. Atomically rename the database temp to its final database name through the already validated parent-directory handle, then durably sync `backup_root`.
4. Atomically rename the manifest temp to its final sidecar name, then durably sync `backup_root` again. Only this final manifest rename+directory-sync commits the pair.

If any step fails, close every handle in `finally`, remove only safely revalidated temp files when possible, leave any database published without a manifest as an uncommitted orphan, and preserve every previously committed backup pair.

Manifest JSON keys are exactly:

```json
{"byte_size":123,"created_at":"2026-07-14T10:00:00.000000Z","database_filename":"agent-backup-20260714T100000000000Z-0123456789abcdef0123456789abcdef.sqlite3","format_version":1,"reason":"scheduled","schema_revision":"0001_foundation","sha256":"64 lowercase hex characters"}
```

Derive `schema_revision` from the copied database, never from the live source after backup. `null` is valid only when the copied database has no `alembic_version` table; an empty or multi-row version table is invalid for format 1. A non-null value may be the current head or any historical revision returned by the repository's Alembic `ScriptDirectory` graph. `verify_backup()` must revalidate filename pairing, regular-file/reparse safety, opened-handle final paths, exact manifest schema, size, SHA-256, `quick_check`, and exact equality between manifest revision and the copied database's revision; reject unknown revisions but do not reject a known historical revision merely because it is not head.

- [ ] **Step 2: Implement safe restore and retention**

`restore_verified_backup()` first calls `verify_backup`. Callers must hold the instance lock, have stopped/joined maintenance workers, and have disposed all application connections. Restore through the SQLite Backup API into an exclusively created, no-follow, destination-adjacent temporary database; quick-check it, verify its embedded revision again, close SQLite, fsync the temp database, and sync the destination directory before publication.

Before replacement, safely quiesce an existing destination through SQLite itself: open it with the bounded operation control, require `PRAGMA wal_checkpoint(TRUNCATE)` to report non-busy, require `PRAGMA journal_mode=DELETE` to return `delete`, and close the connection. This is the only allowed WAL/SHM reset path; never unlink, rename, copy, or inspect `agent.db-wal`/`agent.db-shm` directly. A busy checkpoint, active connection, or failed mode transition aborts before rename. Then atomically replace the destination with the durable temp database through the validated parent handle, sync the destination directory, reopen the published database, rerun `quick_check`/revision validation, restore `PRAGMA journal_mode=WAL`, and close it. Failure before rename leaves the old destination intact; failure after publication is reported as a sanitized restore failure and never causes unsafe sidecar manipulation.

`prune_backup_root()` enumerates at most `max_entries + 1` total directory entries, checking cancellation/deadline between entries. Stage 1G deliberately uses fail-closed complete inventories rather than a persistent cursor: if the extra entry exists or enumeration fails, emit a sanitized bounded-inventory diagnostic and delete nothing at all during that run. Only after a complete inventory may it ignore unrecognized names, remove safely revalidated stale temp/orphan files, keep the newest verified backup regardless of age, and keep at most `retain_count` verified pairs not older than `retention_age`. Never follow links/reparse points, never delete outside the validated `backup_root`, and durably sync the directory after a deletion batch.

- [ ] **Step 3: Wire verified pre-migration backup**

While the Alembic lock is held, call `create_verified_backup(..., reason="pre_migration")` only when `agent.db` exists and has non-zero size. A backup or verification failure aborts migration before schema mutation. A new empty data root receives no meaningless backup.

- [ ] **Step 4: Add tests after implementation**

Cover writes during online backup; hash/size/schema/quick-check verification; exact manifest/database revision equality; accepted `null`, current-head, and known historical revisions; rejected unknown/empty/multi-row revisions; corrupt manifest/database rejection; temp-file fsync -> database rename -> directory sync -> manifest rename -> directory sync ordering; database-first/manifest-last commit behavior; previous backup survival after failure; restore temp fsync/rename/directory-sync ordering; restore quiescence through TRUNCATE + `journal_mode=DELETE`; refusal while readers/writers are active; absence of direct WAL/SHM manipulation; restore equivalence; newest-backup preservation; zero deletion from an incomplete bounded inventory; orphan cleanup after a complete inventory; unrecognized-file preservation; ancestor junction/symlink and opened-handle final-path rejection; and pre-migration backup creation before upgrade from both a historical revision and a valid pre-Alembic database.

- [ ] **Step 5: Verify and commit**

```powershell
$repo = 'D:\AgentProgram\.worktrees\backend-stage1'
$backend = Join-Path $repo 'backend'
Push-Location $backend
try {
    uv run pytest tests/integration/test_database_backup.py tests/migration/test_foundation_migration.py -q
    uv run mypy src/agent_platform/infrastructure/database/backup.py
} finally {
    Pop-Location
}
git -C $repo add -- backend/src/agent_platform/infrastructure/database/backup.py backend/migrations/env.py backend/tests/integration/test_database_backup.py backend/tests/migration/test_foundation_migration.py
git -C $repo commit -m "feat: add verified sqlite backups"
```

### Task 5: Run maintenance and enforce the complete lifecycle

**Files:**

- Create: `backend/src/agent_platform/infrastructure/database/maintenance.py`
- Create: `backend/tests/integration/test_database_maintenance.py`
- Modify: `backend/src/agent_platform/bootstrap/lifespan.py`
- Modify: `backend/src/agent_platform/interfaces/api/routes/health.py`
- Modify: `backend/src/agent_platform/infrastructure/database/__init__.py`
- Modify: `backend/src/agent_platform/infrastructure/logging/files.py`
- Modify: `backend/tests/integration/test_application_lifespan.py`
- Modify: `backend/tests/unit/test_logging_files.py`

- [ ] **Step 1: Implement the maintenance service**

`run_forever()` sleeps for `database_maintenance_interval_seconds`, then calls `run_once()`. Each run always performs PASSIVE checkpoint, database-size measurement, backup retention, and Stage 1E log retention through:

```python
prune_stale_log_files(
    settings.log_root,
    retention_age=settings.log_file_retention_age,
    max_entries=settings.database_maintenance_max_entries_per_run,
)
```

This is the only Stage 1G change to the Stage 1E logging contract: extend `prune_stale_log_files()` with required `max_entries`, and extend the rollover/configuration path so rotation passes the same bounded setting. Like backup retention, it enumerates at most `max_entries + 1` total entries and performs zero deletion when inventory is incomplete; do not edit the Stage 1E plan retroactively. Add the bounded/incomplete-inventory tests in Stage 1G.

Run full integrity and online backup only when their independent monotonic deadlines are due; `force_integrity`/`force_backup` bypass only those deadlines for internal tests. All blocking operations use the cooperative runner from Task 3. `DatabaseMaintenance` owns and exposes no detached worker: cancellation/deadline sets the operation signal, joins the worker, retrieves its result, and only then returns or re-raises; `stop()` is idempotent and confirms the task plus active worker have exited. Update `DatabaseHealthSnapshot` atomically after each operation. Expected busy/backup failures become sanitized structured diagnostic categories and remain retryable; cancellation is re-raised after the join; an unexpected programming failure terminates the task so lifespan retrieves it.

- [ ] **Step 2: Integrate startup and state**

Use the Stage 1E logging signature with only the bounded-prune extension defined above:

```python
logging_runtime = configure_logging(
    settings.log_root,
    settings.log_level,
    max_bytes=settings.log_file_max_bytes,
    retained_file_count=settings.log_file_retained_count,
    retention_age=settings.log_file_retention_age,
    max_entries_per_prune=settings.database_maintenance_max_entries_per_run,
)
```

Startup order is exact:

```text
ensure_directories
instance_lock.acquire
register_known_secret
configure_logging
create_database
probe_database
require quick_check
construct WorkerSupervisor
start Worker Watchdog
construct/start DatabaseMaintenance
publish app.state
```

Publish `instance_lock`, `logging_runtime`, `database`, `worker_supervisor`, `worker_watchdog_task`, `database_maintenance`, and `database_maintenance_task`. Keep the Stage 1E `SecretRegistration` local and active for the complete lifespan. Readiness returns `warnings: ["database_size"]` only when `database_maintenance.snapshot().size_warning` is true; size warning does not make a healthy database unready.

- [ ] **Step 3: Implement strict cleanup order**

Extend `_shutdown_resources` without replacing its first-error/sanitized-secondary-note behavior. Stage 1G order is exact and reserves the documented insertion point for Stage 1H:

```text
cancel/await Worker Watchdog
stop all Workers
cancel/await Database Maintenance and join its active worker
[Stage 1H bounded Outbox drain inserts here]
run final bounded TRUNCATE checkpoint and join its worker
dispose Database
close LoggingRuntime
close SecretRegistration
release ApplicationInstanceLock
```

Every later step runs after any earlier recoverable failure, except that releasing the instance lock is forbidden until the maintenance service, every tracked database worker, and the logging writer have confirmed exit. A database-operation cancellation/timeout therefore may delay cleanup, but cannot detach the thread and continue to database disposal or unlock.

Add one internal `FatalShutdownRequired(BaseException)` plus injectable `_fatal_process_exit()` (`os._exit(70)` in production). Catch `LoggingDrainTimeout` before the broad cleanup accumulator and raise `FatalShutdownRequired` immediately; do not close the secret registration, clear app ownership state, or release the instance lock. The outer lifespan catches the signal before primary-error preservation, sets a fail-stop flag, invokes `_fatal_process_exit()`, and its `finally` skips `_clear_resource_state()` while that flag is set. A test callback may raise a sentinel, which must bypass every broad `except BaseException`; if it returns, raise a fixed `AssertionError`. Stage 1H reuses this generic mechanism for a non-cooperative Outbox Dispatcher.

Startup failure cleans only acquired/created resources in the same relative order and joins any startup `quick_check` worker before unlock. `_clear_resource_state()` removes every new state attribute on normal and recoverable exits. Ordinary synchronous logging/secret-registration `close()` and lock `release()` failures participate in the same error accumulator and never leak exception text.

- [ ] **Step 4: Add lifecycle and maintenance tests after implementation**

Cover exact startup/shutdown ordering, startup quick-check before readiness, cooperative maintenance cancellation and worker-result retrieval, a deliberately blocked worker proving database disposal/unlock cannot overtake confirmed thread exit, final checkpoint before dispose, lock release last, logging close and secret unregistration before lock release, every safe cleanup step after partial failures, original body/startup/cancellation error preservation, sanitized secondary notes, app-state clearing, periodic deadlines, size warning transition, bounded log/backup retention calls, and zero log/backup deletion when either inventory is incomplete. Add an injected `LoggingDrainTimeout` case proving the generic fail-stop signal bypasses the accumulator and that secret unregistration, state clearing, and lock release do not occur. In `tests/process/test_logging_fail_stop.py`, block the real writer, request shutdown, and prove production exits with code 70 within the logging deadline without plaintext/raw-secret output; release/restart verification then proves SQLite and the data root remain recoverable.

- [ ] **Step 5: Verify and commit**

```powershell
$repo = 'D:\AgentProgram\.worktrees\backend-stage1'
$backend = Join-Path $repo 'backend'
Push-Location $backend
try {
    uv run pytest tests/unit/test_logging_files.py tests/process/test_logging_fail_stop.py tests/integration/test_database_maintenance.py tests/integration/test_application_lifespan.py tests/contract/test_system_api.py -q
    uv run ruff check src/agent_platform/bootstrap/lifespan.py src/agent_platform/infrastructure/database src/agent_platform/infrastructure/logging/files.py src/agent_platform/interfaces/api/routes/health.py tests/unit/test_logging_files.py tests/process/test_logging_fail_stop.py tests/integration/test_database_maintenance.py tests/integration/test_application_lifespan.py
} finally {
    Pop-Location
}
git -C $repo add -- backend/src/agent_platform/bootstrap/lifespan.py backend/src/agent_platform/infrastructure/database backend/src/agent_platform/infrastructure/logging/files.py backend/src/agent_platform/interfaces/api/routes/health.py backend/tests/unit/test_logging_files.py backend/tests/process/test_logging_fail_stop.py backend/tests/integration/test_database_maintenance.py backend/tests/integration/test_application_lifespan.py backend/tests/contract/test_system_api.py
git -C $repo commit -m "feat: run bounded sqlite maintenance"
```

### Task 6: Run Stage 1G regression gates and freeze the handoff

**Files:**

- Modify only if a gate exposes a Stage 1G defect in files listed above.

- [ ] **Step 1: Prove no immutable or unrelated scope drift**

```powershell
$repo = 'D:\AgentProgram\.worktrees\backend-stage1'
git -C $repo show-ref --verify --quiet refs/codex/stage1g-base
if ($LASTEXITCODE -ne 0) { throw 'Missing frozen refs/codex/stage1g-base.' }
git -C $repo diff --exit-code refs/codex/stage1g-base..HEAD -- backend/migrations/versions/0001_foundation.py
git -C $repo diff --exit-code HEAD -- backend/migrations/versions/0001_foundation.py

$forbidden = & rg -n "copyfile|copy2|agent\.db-wal|agent\.db-shm|unlink\(.*event_log|DELETE FROM event_log" (Join-Path $repo 'backend/src') (Join-Path $repo 'backend/migrations') 2>&1
$rgStatus = $LASTEXITCODE
if ($rgStatus -eq 0) {
    $forbidden
    throw 'Forbidden SQLite sidecar copy/delete or EventLog deletion reference found.'
}
if ($rgStatus -ne 1) {
    $forbidden
    throw "rg failed with exit code $rgStatus."
}
```

Expected: both the complete Stage 1G commit range and current working tree leave the foundation migration unchanged. `rg` exit `1` is the successful no-match result; exit `0` fails the gate and exit greater than `1` is a search error.

- [ ] **Step 2: Run focused Stage 1G regression**

```powershell
$repo = 'D:\AgentProgram\.worktrees\backend-stage1'
$backend = Join-Path $repo 'backend'
Push-Location $backend
try {
    uv run pytest tests/unit/test_database_instance_lock.py tests/unit/test_database_integrity.py tests/unit/test_logging_files.py tests/process/test_logging_fail_stop.py tests/integration/test_database_backup.py tests/integration/test_database_maintenance.py tests/integration/test_database_bootstrap.py tests/integration/test_application_lifespan.py tests/migration/test_foundation_migration.py tests/contract/test_system_api.py -q
} finally {
    Pop-Location
}
```

Expected: all selected tests pass, including real Windows multi-process lock coverage.

- [ ] **Step 3: Run the complete backend gate**

```powershell
$repo = 'D:\AgentProgram\.worktrees\backend-stage1'
$backend = Join-Path $repo 'backend'
Push-Location $backend
try {
    uv run ruff format --check .
    uv run ruff check .
    uv run mypy src
    uv run pytest
} finally {
    Pop-Location
}
```

Expected: all four commands exit `0`; existing Stage 0 and Stage 1A–1F tests remain green.

- [ ] **Step 4: Self-review and commit gate-only corrections**

Check that Backend and Alembic share the exact lock class/path, quick-check occurs before readiness, full integrity remains internal, backup verification is mandatory before restore/retention, manifest publication is last, maintenance is bounded, database-size warnings are observable, secret registration remains active until logging closes, and lock release is the final cleanup. Then commit only required corrections:

```powershell
$repo = 'D:\AgentProgram\.worktrees\backend-stage1'
$pending = git -C $repo status --short
$pending
if ($pending) {
    git -C $repo add -- backend/src backend/migrations backend/tests
    git -C $repo commit -m "test: close sqlite resilience regressions"
}
```

If the repository-root status is empty after all gates, do not create an empty commit. Remove the temporary baseline ref only after review completes: `git -C $repo update-ref -d refs/codex/stage1g-base`.

## Stage 1H handoff contract

Stage 1H may add Outbox Dispatcher resources without changing Stage 1G interfaces. It inserts dispatcher startup after `database_maintenance_task`, and inserts bounded dispatcher drain after database-maintenance cancellation but before `database_maintenance.final_checkpoint()`. The final order remains Workers -> maintenance -> Outbox drain -> checkpoint -> database -> logging -> secret unregistration -> instance lock.
