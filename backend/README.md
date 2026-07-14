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

## Verification

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Worker stdout is reserved for framed protocol messages. Worker logs and diagnostics use stderr.
