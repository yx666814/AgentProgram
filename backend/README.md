# Agent Platform Backend

Windows-first local backend for the contract-driven five-stage multi-agent workflow.

## Prerequisites

- Windows with Python 3.12
- [`uv`](https://docs.astral.sh/uv/)

Run all commands below from the `backend` directory.

## Setup

```powershell
uv sync --group dev
```

Set a local session token and a writable data root. The token value below is a development
placeholder and must be replaced for each environment.

```powershell
$env:AGENT_PLATFORM_SESSION_TOKEN = "change-me-for-local-development"
$env:AGENT_PLATFORM_DATA_ROOT = "$env:LOCALAPPDATA\AgentProgram"
$env:AGENT_PLATFORM_HOST = "127.0.0.1"
$env:AGENT_PLATFORM_PORT = "0"

uv run alembic upgrade head
uv run agent-platform-backend
```

The launcher reads all settings from the environment. The V1 backend only accepts the loopback
host `127.0.0.1`; port `0` lets the operating system select an available local port. Apply
migrations before starting the API because the production lifespan does not create database
tables.

Runtime diagnostics are written as bounded UTF-8 JSON Lines to
`$AGENT_PLATFORM_DATA_ROOT/logs/backend.jsonl` and mirrored to stderr. Uvicorn access/error
records use the same redaction path after application startup; unknown Worker stderr is stored
only as byte count, SHA-256, and safety flags. Optional logging controls are:

- `AGENT_PLATFORM_LOG_FILE_MAX_BYTES`
- `AGENT_PLATFORM_LOG_RECORD_MAX_BYTES`
- `AGENT_PLATFORM_LOG_FILE_RETAINED_COUNT`
- `AGENT_PLATFORM_LOG_FILE_RETENTION_DAYS`
- `AGENT_PLATFORM_LOG_QUEUE_CAPACITY`
- `AGENT_PLATFORM_LOG_SHUTDOWN_DRAIN_SECONDS`

IPC v1 requires positive consecutive sequence numbers in both directions. Recent message IDs are
retained only as SHA-256 digests in a per-process replay window. Configure its capacity with
`AGENT_PLATFORM_WORKER_IPC_REPLAY_WINDOW_CAPACITY` (default `4096`, supported `64`–`65536`).
Wire message IDs are limited to 128 characters; the IPC protocol version remains `1`.

The Backend and online Alembic migrations share `runtime/backend.lock`, so one data root has only
one owner. Startup runs SQLite `quick_check`; background maintenance performs bounded WAL
checkpoints, integrity checks, verified SQLite backups under `backups/`, retention, and database
size warnings. Relevant environment settings use the `AGENT_PLATFORM_DATABASE_` prefix, including
`OPERATION_TIMEOUT_SECONDS`, `MAINTENANCE_INTERVAL_SECONDS`,
`INTEGRITY_CHECK_INTERVAL_SECONDS`, `BACKUP_INTERVAL_SECONDS`,
`BACKUP_RETAINED_COUNT`, `BACKUP_RETENTION_DAYS`, and `SIZE_WARNING_BYTES`.

Every persisted `EventEnvelope` is written atomically with one Outbox aggregate and the required
`local_audit_v1` delivery target. The Dispatcher uses short SQLite leases, bounded retry/backoff,
dead-letter state, and at-least-once delivery. The local audit projection excludes event payloads
and records its idempotent side effect and delivery receipt in one transaction.

Stage 3 persists workflows, five ordered stage runs, rooms, immutable sequenced messages, and a
conditional task queue. Authenticated REST commands create/start workflows, transition or reopen
stages, append discussion/correction/consultation messages, and queue/start/complete/cancel tasks.
Workflow events add the `websocket_v1` Outbox target. Clients request a short-lived single-use
ticket at `POST /api/v1/events/tickets`, connect to `/api/v1/events/ws`, and send the last observed
`event_id` as `after_event_id`; committed events are replayed from SQLite before gap-free live
delivery. Optional controls are:

- `AGENT_PLATFORM_WEBSOCKET_TICKET_TTL_SECONDS`
- `AGENT_PLATFORM_WEBSOCKET_REPLAY_BATCH_SIZE`
- `AGENT_PLATFORM_WEBSOCKET_SUBSCRIBER_QUEUE_CAPACITY`
- `AGENT_PLATFORM_WEBSOCKET_PUBLISHER_DEDUP_CAPACITY`

Stage 4 adds versioned model profiles and room assignments without accepting or persisting API
keys. Profiles contain only `credential_ref` and `masked_hint`; the default standalone backend
registers an unavailable SecretStore implementation, while the desktop integration will inject
the real OS-backed resolver. OpenAI-compatible and Anthropic adapters stream provider responses
through a cancellation-aware interface. Agent runs use an idempotent room request key, support a
primary-only discussion path, and require Primary + Reviewer A + Reviewer B for formal P0/P1/P2R
delivery. Final outputs are atomically stored under `model-outputs/` by SHA-256 reference; SQLite
stores only references, hashes, sizes, call state, and token usage. NDJSON streaming is available
at `POST /api/v1/agent-runs/{run_id}/stream`. Optional controls are:

- `AGENT_PLATFORM_MODEL_OUTPUT_MAX_BYTES`
- `AGENT_PLATFORM_MODEL_CONTEXT_MAX_CHARACTERS`
- `AGENT_PLATFORM_MODEL_SUMMARY_TRIGGER_CHARACTERS`
- `AGENT_PLATFORM_MODEL_SUMMARY_MAX_CHARACTERS`
- `AGENT_PLATFORM_MODEL_MAX_OUTPUT_TOKENS`
- `AGENT_PLATFORM_MODEL_HTTP_TIMEOUT_SECONDS`
- `AGENT_PLATFORM_PROJECT_INSTRUCTION_MAX_BYTES`

Stage 5 completes the backend V1 execution and governance chain. A versioned Tool Catalog and
PathGuard enforce StageContract capabilities, approved task-scoped escalation, project-relative
paths, excluded paths, artifact ownership, and permanent prohibitions. File writes use verified
atomic replacement with optimistic hashes. Registered project commands run without a shell,
inside a kill-on-close Windows Job Object, with bounded output, timeout, cancellation, and
process-tree cleanup. Tool audit rows persist only hashes, sizes, exit state, and sanitized error
codes; raw file contents and command output are returned only to the active caller.

ArtifactVersion, deterministic Quality Gate, Approval, Checkpoint, HandoffPacket, and
ChangeRequest now form one backend-controlled completion chain. MANUAL mode waits for a user
decision; AUTONOMOUS PASS completes the handoff, while AUTONOMOUS WARNING enters
`warning_blocked` and creates a rewrite request. Pause, resume, stop, abandon, restart recovery,
and task-scoped capability expiry are exposed through authenticated REST commands. Desktop
control v1 is available at `GET /api/v1/system/control` and `POST /api/v1/system/shutdown`.
Product-internal Git tools remain intentionally unimplemented.

Optional Stage 5 limits are:

- `AGENT_PLATFORM_TOOL_FILE_MAX_BYTES`
- `AGENT_PLATFORM_TOOL_OUTPUT_MAX_BYTES`

## Verification

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Worker stdout is reserved for framed protocol messages. Worker logs and diagnostics use stderr.
