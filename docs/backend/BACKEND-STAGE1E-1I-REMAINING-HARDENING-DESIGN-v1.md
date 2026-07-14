# Backend Stage 1E–1I Remaining Hardening Design

> Status: implemented and verified; Stage 2 may begin.

## 1. Purpose

Stage 1A–1D froze the shared contracts, role resources, stage policy, version/schema sources, launcher, and Worker Watchdog. They did not complete every Stage 1 requirement in `docs/PROJECT-PLAN.md`.

Stage 1E–1I completes the remaining foundation hardening before Stage 2 begins:

- durable Backend logs and bounded Worker stderr evidence;
- bounded bidirectional IPC replay protection;
- SQLite single-instance ownership, integrity checks, online backups, WAL maintenance, and safe retention;
- complete EventEnvelope persistence and a reliable transactional Outbox;
- migration, regression, security, and independent-review closure for the whole Stage 1 branch.

## 2. Delivery and process rules

The implementation order is fixed:

```text
Stage 1E Runtime Diagnostics
-> Stage 1F IPC Replay Hardening
-> Stage 1G SQLite Resilience
-> Stage 1H Durable Events and Reliable Outbox
-> Stage 1I Stage 1 Closure
```

At the user's explicit direction, Stage 1E–1I will not use test-first TDD. Each task instead follows:

```text
implement the approved behavior
-> add focused automated tests
-> run focused regression
-> run complete Stage 1 gate
```

Tests, migration rollback coverage, static analysis, and independent review remain mandatory.

## 3. Explicit non-goals

Stage 1E–1I does not implement:

- Project, Workspace, Manifest, snapshot, restore, or FileConflict behavior from Stage 2;
- Workflow, Room, Task, WebSocket, or event replay APIs from Stage 3;
- model providers, prompts, or agent execution from Stage 4;
- shell/file/build/test tools or product-internal Git from Stage 5;
- Electron port publication, temporary session-token rotation, diagnostic export UI, or upgrade orchestration from Stage 8;
- Worker automatic restart or a new IPC wire version;
- deletion or retention management of user project files, Direct Workspaces, EventLog history, or future Stage 2 snapshots.

## 4. Shared lifecycle and failure rules

The Backend Main Process remains the only authority over SQLite, Outbox delivery, Worker state, logging, and maintenance tasks.

Startup order:

```text
ensure application directories
-> acquire the application instance lock
-> register the current session token as a known secret
-> configure durable logging
-> open and probe SQLite
-> run quick integrity validation
-> construct WorkerSupervisor and Watchdog
-> start database maintenance
-> start Outbox Dispatcher
-> expose application state
```

Shutdown order:

```text
cancel and await Worker Watchdog
-> stop all Workers
-> cancel and await database maintenance
-> bounded drain and stop Outbox Dispatcher
-> run final bounded WAL checkpoint
-> dispose SQLite
-> flush and close durable logging
-> unregister the current session token
-> release the application instance lock
```

Stopping Workers before the final Outbox drain ensures shutdown events can still be claimed. If the graceful drain expires, the Dispatcher is cancelled and receives a second short bounded cleanup deadline; normally leased rows then remain recoverable after lease expiry on the next startup. If a non-cooperative Dispatcher exceeds that second deadline, or the logging writer remains alive after its own close deadline, the Backend fails stop instead of disposing/releasing resources underneath live work. Every ordinary cleanup step runs even if an earlier step fails; these ownership-dependency breaches are the only exceptions. The first error remains primary. Later cleanup failures add only the existing sanitized cleanup note and never expose paths, payloads, stderr content, credentials, or exception messages.

## 5. Stage 1E: Runtime Diagnostics

### 5.1 Backend logging

The existing structlog and stdlib pipeline remains the single logging path. It gains two synchronized outputs:

- stderr JSON for the local launcher and development diagnostics;
- rotating UTF-8 JSON Lines at `log_root/backend.jsonl`.

Settings define and validate bounded file size, final UTF-8 record size, queue capacity, retained file count, retention age, and logging-drain deadline. Each caller reduces a record to one fully redacted immutable bounded JSON line and enqueues it without sink I/O; one writer thread exclusively owns stderr/file writes and rotation, so slow storage cannot block the asyncio IPC loop. No live `LogRecord`, exception, argument object, or raw secret remains in the queue. Rotation uses application-owned files with fixed names under `log_root`; active files, rollover paths, and cleanup reject links/reparse points and never mutate files outside the handle-verified log directory.

The shared redaction implementation owns sensitive keys, a runtime registry of known secret values, and safe scalar rendering so API errors, Backend logs, and Worker evidence do not maintain drifting secret lists. The current session token is registered at startup. Registered values are removed even when embedded in ordinary strings, URLs, Bearer headers, or exception text.

External exception messages and request values are never logged directly; only stable internal categories and exception types may be emitted. Each structured record contains a UTC timestamp, level, logger, event name, and available safe context identifiers such as correlation, project, workflow, room, task, and worker IDs. Request bodies, model payloads, full project paths, session tokens, and raw credentials are never logged.

Uvicorn's independent handlers are disabled before the server starts. Pre-lifespan Uvicorn records are safely suppressed; after lifespan configures diagnostics, `uvicorn.error` and `uvicorn.access` propagate through the same bounded JSON/redaction queue, and post-lifespan records return to suppression rather than plaintext fallback.

### 5.2 Worker stderr evidence

`WorkerSupervisor` continues draining stderr continuously so a flood cannot block IPC or shutdown.

First-party Worker stderr lines that match the approved safe diagnostic grammar are emitted as structured Backend log records with `source=worker`, `worker_id`, and `project_id`.

Unknown, invalid UTF-8, oversized, or otherwise unsafe stderr is not persisted as raw text. The record contains only:

- byte count;
- SHA-256 digest;
- truncation/encoding flags;
- worker and project identifiers.

Reads are chunked and line assembly is bounded. A stderr flood may create rate-limited summary records but cannot create unbounded memory, unbounded files, or backpressure on Worker stdout IPC.

## 6. Stage 1F: IPC Replay Hardening

A shared replay-window component is used by both the Backend supervisor and Worker runtime.

Rules:

- inbound sequence numbers are strict positive consecutive integers;
- duplicate, skipped, reversed, boolean, float, or string sequence values fail closed;
- wire message IDs have a fixed maximum length and recently seen IDs are retained only as fixed-size SHA-256 digests in a fixed-capacity deque-plus-set window;
- the default capacity is 4096 and is validated within a bounded configured range;
- eviction removes digests from both the deque and set; raw message IDs are never retained by replay state;
- memory use remains bounded for a Worker that runs indefinitely;
- the Worker process lifetime remains the IPC session boundary;
- no field is added to IPC v1 and no automatic Worker restart is introduced.

Strict sequence validation remains the primary replay defense. The bounded ID window detects near-term message-ID reuse without retaining every heartbeat ID forever.

## 7. Stage 1G: SQLite Resilience

### 7.1 Single-instance ownership

The application owns an operating-system advisory lock at `runtime_root/backend.lock`.

- Windows uses a real exclusive file lock, not a PID-file existence check.
- POSIX tests use the platform advisory-lock equivalent.
- lock metadata may record PID, version, and UTC acquisition time for diagnostics, but metadata is never trusted as ownership proof.
- Backend startup and online Alembic migration use the same lock boundary.
- the lock is acquired before database creation and released only after database disposal.

A second owner receives a stable unavailable error without learning another process's command line or environment.

### 7.2 Integrity and WAL maintenance

Startup runs SQLite `quick_check` before the application becomes ready. A full `integrity_check` operation is available to internal maintenance and tests but is not exposed as a public API in Stage 1.

WAL checkpoint operations are bounded by timeout and report busy state without deleting or copying WAL/SHM files. Maintenance never blocks shutdown indefinitely.

### 7.3 Verified online backups

Backups use SQLite's online Backup API through a dedicated synchronous connection executed off the event loop. Direct copying of `.db`, `-wal`, or `-shm` files is forbidden.

A committed backup consists of:

- an atomically published SQLite file under `backup_root`;
- a sidecar manifest containing schema revision, creation UTC, byte size, and SHA-256;
- a successful `quick_check` of the backup before publication.

The database and manifest are first written as temporary files. The database file is published first and the manifest is atomically published last as the commit marker. Restore and retention accept only a complete file pair whose size, Hash, schema revision, and `quick_check` are revalidated. Orphan temporary files and final database files without a valid manifest are never treated as backups and are removed by bounded maintenance.

Failed temporary backups are removed without replacing the previous valid backup. Online Alembic upgrade creates a verified pre-migration backup of an existing database while holding the same instance lock.

Retention applies only to recognized application-owned backup and log filenames, retains the newest valid backup, rejects symbolic links/reparse-point escapes, and never touches project or snapshot data. SQLite retention in Stage 1 is a foundation: delivered Outbox aggregates and target rows are bounded, while EventLog and unresolved dead letters remain protected until Stage 3 freezes replay and acknowledgement watermarks. Configured database-size thresholds produce a health warning before unbounded growth becomes an unnoticed failure.

## 8. Stage 1H: Durable Events and Reliable Outbox

### 8.1 Migration and EventEnvelope persistence

A new immutable Alembic revision follows `0001_foundation`; the foundation migration is never edited.

The migration upgrades EventLog persistence so every row can reconstruct the frozen `EventEnvelope`:

- `schema_version`;
- event type and positive event ID;
- correlation and optional causation ID;
- actor type and optional actor ID;
- source;
- occurred-at UTC;
- project/workflow/room/task identifiers;
- aggregate type/ID;
- strict JSON payload.

Before mutation, every legacy foundation row is preflight-validated against the exact strict envelope, identifier, aggregate, payload, timestamp, and Outbox relationship rules because SQLite does not enforce declared `String(N)` lengths. Valid rows are backfilled deterministically with schema version 1, system/backend attribution, preserved timestamps, and generated stable legacy correlation identifiers before non-null constraints are enforced. Any invalid legacy row aborts the upgrade with a sanitized category/count error and leaves the `0001` database unchanged; the migration never silently truncates or rewrites user data.

Repository writes accept validated event contracts rather than loose unvalidated payload dictionaries.

### 8.2 Outbox state machine

`outbox_events` remains the one-per-event aggregate. A new `outbox_deliveries` row is created for every immutable target and is unique by `(event_id, consumer_name)`. Delivery-row states are closed values:

```text
pending
leased
retry_wait
delivered
dead_letter
```

Delivery rows include lease owner/expiry, next-attempt time, bounded attempt count, delivered/dead-letter timestamps, and a sanitized last-error category. The aggregate row records whether every target is delivered or any target is unresolved/dead-lettered. Raw exception messages and payloads are not stored as error diagnostics.

Claiming uses one short atomic SQLite `UPDATE ... WHERE id=(SELECT ... LIMIT 1) RETURNING` transaction, with only classified busy/snapshot contention receiving a small bounded retry. A deferred `SELECT`-then-`UPDATE` claim is forbidden. Publishing happens outside the claim transaction. Confirmation uses the lease token so an expired owner cannot acknowledge another owner's claim.

Retry uses deterministic exponential backoff with a configured maximum. Expired leases return to eligibility. Exceeding the configured attempt limit moves the item to dead letter while retaining EventLog history.

### 8.3 Immutable delivery targets and consumer idempotency

Publishers implement a small application port with a stable consumer name and an async publish operation receiving a reconstructed `EventEnvelope` plus the persisted event ID as its idempotency key.

The target consumer set is created transactionally when the EventLog and Outbox records are inserted. Each immutable delivery target has its own lease, retry, delivery, and dead-letter state. Restarting the process or changing the runtime publisher registry cannot silently remove a target or mark an event delivered early.

Consumers must make their side effect idempotent by event ID. A local database consumer writes its side effect and successful receipt in the same transaction. An external or file-based consumer may repeat after a crash between side effect and acknowledgement; duplicate delivery is therefore permitted and always carries the same event ID. The platform guarantees at-least-once delivery, not exactly-once external side effects.

A delivered target row is the coordinator receipt. A retry skips a target already marked delivered. The aggregate Outbox record becomes delivered only when every immutable target created at enqueue time is delivered or explicitly resolved by a future versioned administrative operation.

Stage 1 requires the immutable target `local_audit_v1`; no Unit of Work configuration may omit it. It writes a payload-free SQLite audit projection keyed by event ID and marks the target delivered in the same transaction, making retries logically idempotent. The projection contains only event identity, type, correlation context, occurred-at time, and delivered-at time.

Durable JSONL logging may observe successful audit delivery, but it is non-authoritative and is not an Outbox target; duplicate log observations after a crash are harmless because readers can deduplicate by event ID. Stage 3 may add WebSocket delivery for newly enqueued events separately and uses EventLog replay for historical events.

Automatic cleanup atomically removes old delivered aggregate rows and their delivered target rows only after every immutable target is terminal and the event can no longer be re-enqueued by supported code paths. EventLog and unresolved dead letters are retained. Database size and protected-row counts are monitored; no user data is deleted.

## 9. Stage 1I: Closure

Stage 1I contains no new product feature. It closes the milestone with:

- migration tests for foundation -> head, legacy-data upgrade, downgrade, and re-upgrade;
- durable-log rotation, retention, secret-redaction, invalid-UTF-8, and flood tests;
- bidirectional sequence/replay and bounded-memory IPC tests;
- multi-process instance-lock tests on Windows;
- backup hash, quick-check, corrupt-backup rejection, WAL checkpoint, retention, and restore verification;
- Outbox claim race, lease expiry, crash-after-publish, retry, dead-letter, consumer receipt, cleanup, and cancellation tests;
- lifecycle startup/shutdown ordering and partial-failure cleanup tests;
- stale-literal and migration-revision checks;
- complete Ruff format, Ruff lint, Mypy strict, and pytest gates;
- an independent code review with all Critical and Important findings resolved.

Stage 2 may begin only after Stage 1I passes and the Stage 1 branch remains clean.

## 10. Acceptance criteria

Stage 1E–1I is complete only when all of the following are true:

1. Backend and safe Worker diagnostics survive process exit in bounded rotating files without known secret leakage.
2. Long-lived Workers do not grow replay-detection memory without bound, and both IPC directions reject invalid sequence/replay input.
3. A second Backend cannot own the same data root concurrently.
4. SQLite backups are online, atomically published, hash-verified, and integrity-checked.
5. WAL maintenance and retention are bounded and restricted to application-owned paths.
6. Persisted events reconstruct the approved EventEnvelope.
7. Outbox delivery is at least once, retryable, lease-safe, dead-lettered after a bound, and idempotent per consumer.
8. Shutdown retrieves every background-task result and completes all later cleanup steps.
9. Existing Stage 0 and Stage 1A–1D behavior remains compatible.
10. The complete Stage 1 quality gate and independent review pass with no unresolved Critical or Important issue.
