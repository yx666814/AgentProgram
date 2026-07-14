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

## Verification

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Worker stdout is reserved for framed protocol messages. Worker logs and diagnostics use stderr.
