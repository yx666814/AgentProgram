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

uv run alembic upgrade head
uv run uvicorn agent_platform.bootstrap.app_factory:dev_app --factory
```

`dev_app()` reads both settings from the environment. Apply migrations before starting the API;
the production lifespan does not create database tables.

## Verification

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Worker stdout is reserved for framed protocol messages. Worker logs and diagnostics use stderr.
