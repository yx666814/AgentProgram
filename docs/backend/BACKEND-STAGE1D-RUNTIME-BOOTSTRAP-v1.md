# Backend Stage 1D Runtime Bootstrap Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove bootstrap version/schema drift, launch the API from validated host/port settings, and run Worker heartbeat supervision throughout the application lifespan.

**Architecture:** Package metadata is the sole backend-version source. A database schema module owns immutable historical Alembic revisions plus the current readiness revision. A small production launcher constructs Settings and passes its host/port to Uvicorn. Lifespan owns a cancellable watchdog task that repeatedly invokes `WorkerSupervisor.watch_once()` and is shut down before workers and the database.

**Tech Stack:** Python 3.12, importlib.metadata, FastAPI, Uvicorn, Alembic, asyncio, Pydantic Settings, pytest, Ruff, mypy.

---

## File Map

```text
backend/src/agent_platform/
|- version.py                              # package-metadata version source
|- __init__.py                             # re-export __version__
|- main.py                                 # validated production launcher
|- bootstrap/{app_factory.py,lifespan.py} # version use and Watchdog ownership
|- config/settings.py                      # loopback host/port/watchdog validation
`- infrastructure/database/schema.py       # historical/current revisions and required tables

backend/migrations/versions/0001_foundation.py
backend/tests/
|- unit/test_version.py
|- unit/test_main.py
|- unit/test_settings.py
|- migration/test_foundation_migration.py
|- contract/test_system_api.py
`- integration/test_application_lifespan.py

backend/{pyproject.toml,README.md}
```

## Explicit Boundaries

- No dynamic Electron control channel, port publication file, session-token rotation, or desktop process ownership yet.
- No migration is added; the existing foundation revision only receives an immutable named revision constant.
- No Worker stderr persistence, Outbox dispatch, SQLite lock/backup, or retention policy.
- Watchdog only enforces existing heartbeat timeout behavior through `watch_once()`; it does not restart workers or invent recovery state.
- The V1 launcher remains loopback-only and rejects public bind addresses.

### Task 1: Unify backend version source

**Files:**
- Create: `backend/src/agent_platform/version.py`
- Modify: `backend/src/agent_platform/__init__.py`
- Modify: `backend/src/agent_platform/bootstrap/app_factory.py`
- Create: `backend/tests/unit/test_version.py`
- Modify: `backend/tests/contract/test_system_api.py`

- [ ] **Step 1: Write failing package-version tests**

```python
from importlib.metadata import version
from pathlib import Path

import agent_platform
import agent_platform.bootstrap.app_factory as app_factory
import pytest
from agent_platform.bootstrap.app_factory import create_app
from agent_platform.config.settings import Settings


def test_backend_version_comes_from_installed_package_metadata() -> None:
    assert agent_platform.__version__ == version("agent-platform-backend")


def test_fastapi_metadata_uses_backend_package_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_factory, "__version__", "9.8.7", raising=False)
    app = create_app(Settings(data_root=tmp_path, session_token="local-secret"))
    assert app.version == "9.8.7"
```

Keep the existing `/api/v1/system/info` assertion. RED must show FastAPI still contains a hardcoded literal after a test monkeypatches `agent_platform.bootstrap.app_factory.__version__` to a sentinel.

- [ ] **Step 2: Verify RED**

Run:

```powershell
uv run pytest tests/unit/test_version.py tests/contract/test_system_api.py -k "version or system_info" -v
```

- [ ] **Step 3: Implement metadata-backed version source**

`version.py`:

```python
from importlib.metadata import version
from typing import Final

PACKAGE_NAME: Final[str] = "agent-platform-backend"
__version__: Final[str] = version(PACKAGE_NAME)
```

`agent_platform.__init__` re-exports `__version__`. `create_app()` imports that value and passes it to `FastAPI(version=__version__)`; no source file other than package metadata contains `0.1.0` as the backend runtime version.

- [ ] **Step 4: Verify GREEN and commit**

```powershell
uv run pytest tests/unit/test_version.py tests/contract/test_system_api.py -k "version or system_info" -v
uv run ruff check src tests/unit/test_version.py tests/contract/test_system_api.py
uv run mypy src
git add backend/src backend/tests/unit/test_version.py backend/tests/contract/test_system_api.py
git commit -m "fix: unify backend version source"
```

### Task 2: Separate immutable migration revisions from the current database revision

**Files:**
- Create: `backend/src/agent_platform/infrastructure/database/schema.py`
- Modify: `backend/migrations/versions/0001_foundation.py`
- Modify: `backend/src/agent_platform/interfaces/api/routes/health.py`
- Modify: `backend/tests/migration/test_foundation_migration.py`
- Modify: `backend/tests/contract/test_system_api.py`

- [ ] **Step 1: Write failing revision-consistency tests**

```python
import importlib.util
from pathlib import Path
from types import ModuleType

from agent_platform.infrastructure.database.schema import (
    CURRENT_DATABASE_REVISION,
    FOUNDATION_DATABASE_REVISION,
    REQUIRED_DATABASE_TABLES,
)


def _load_foundation_module() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "migrations/versions/0001_foundation.py"
    spec = importlib.util.spec_from_file_location("foundation_0001", path)
    if spec is None or spec.loader is None:
        raise AssertionError("foundation migration could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_foundation_migration_uses_immutable_foundation_revision() -> None:
    assert _load_foundation_module().revision == FOUNDATION_DATABASE_REVISION


def test_current_database_revision_starts_at_foundation() -> None:
    assert CURRENT_DATABASE_REVISION == FOUNDATION_DATABASE_REVISION


def test_required_foundation_tables_are_shared() -> None:
    assert REQUIRED_DATABASE_TABLES == frozenset(
        {"alembic_version", "event_log", "outbox_events"}
    )
```

Add the helper above to `test_foundation_migration.py`; the numeric migration filename must not be imported with ordinary Python module syntax. Add a test that advances `schema.CURRENT_DATABASE_REVISION` to a sentinel and proves the historical foundation migration remains `FOUNDATION_DATABASE_REVISION`. Add an API contract test that monkeypatches the health module's imported current revision constant to a sentinel and proves readiness uses it. RED must fail because `schema.py` is absent.

- [ ] **Step 2: Implement immutable historical and current schema constants**

```python
FOUNDATION_DATABASE_REVISION: Final[str] = "0001_foundation"
CURRENT_DATABASE_REVISION: Final[str] = FOUNDATION_DATABASE_REVISION
REQUIRED_DATABASE_TABLES: Final[frozenset[str]] = frozenset(
    {"alembic_version", "event_log", "outbox_events"}
)
```

Set the foundation migration module's `revision` from `FOUNDATION_DATABASE_REVISION`; historical migration identifiers must never follow future changes to `CURRENT_DATABASE_REVISION`. Health imports `CURRENT_DATABASE_REVISION` and `REQUIRED_DATABASE_TABLES`, then removes its local `EXPECTED_DATABASE_REVISION` and mutable table set.

- [ ] **Step 3: Verify GREEN and commit**

```powershell
uv run pytest tests/migration/test_foundation_migration.py tests/contract/test_system_api.py -k "revision or readiness" -v
uv run ruff check src migrations tests/migration/test_foundation_migration.py tests/contract/test_system_api.py
uv run mypy src
git add backend/src backend/migrations backend/tests/migration backend/tests/contract/test_system_api.py
git commit -m "fix: share database revision contract"
```

### Task 3: Add validated production launcher

**Files:**
- Create: `backend/src/agent_platform/main.py`
- Modify: `backend/src/agent_platform/config/settings.py`
- Modify: `backend/pyproject.toml`
- Modify: `backend/README.md`
- Create: `backend/tests/unit/test_main.py`
- Modify: `backend/tests/unit/test_settings.py`

- [ ] **Step 1: Write failing settings and launcher tests**

```python
def test_settings_rejects_non_loopback_host(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        Settings(
            host="0.0.0.0",
            data_root=tmp_path,
            session_token="local-secret",
        )


@pytest.mark.parametrize("port", [-1, 65536])
def test_settings_rejects_invalid_port(tmp_path: Path, port: int) -> None:
    with pytest.raises(ValidationError):
        Settings(data_root=tmp_path, session_token="local-secret", port=port)


def test_run_consumes_validated_host_and_port(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        host="127.0.0.1",
        port=43210,
        data_root=tmp_path,
        session_token="local-secret",
    )
    calls: list[tuple[object, str, int]] = []
    monkeypatch.setattr(
        main_module.uvicorn,
        "run",
        lambda app, *, host, port: calls.append((app, host, port)),
    )

    main_module.run(settings)

    assert calls[0][0].state.settings is settings
    assert calls[0][1:] == ("127.0.0.1", 43210)
```

Also test `main()` constructs Settings from environment and delegates to `run()` without exposing the session token. RED must fail because `agent_platform.main` does not exist and host/port are not fully validated.

- [ ] **Step 2: Implement validation and launcher**

Settings rules:

```python
host: Literal["127.0.0.1"] = "127.0.0.1"
port: int = Field(default=0, ge=0, le=65535)
```

`main.py`:

```python
def run(settings: Settings) -> None:
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
    )


def main() -> None:
    run(Settings())
```

Add:

```toml
[project.scripts]
agent-platform-backend = "agent_platform.main:main"
```

README uses `uv run agent-platform-backend` after migrations and documents `AGENT_PLATFORM_HOST=127.0.0.1` plus dynamic `AGENT_PLATFORM_PORT=0`.

- [ ] **Step 3: Verify GREEN and commit**

```powershell
uv run pytest tests/unit/test_main.py tests/unit/test_settings.py tests/unit/test_app_factory.py -v
uv run ruff check src tests/unit/test_main.py tests/unit/test_settings.py
uv run mypy src
git add backend/src backend/tests/unit backend/pyproject.toml backend/README.md
git commit -m "feat: add validated backend launcher"
```

### Task 4: Own Worker Watchdog in application lifespan

**Files:**
- Modify: `backend/src/agent_platform/config/settings.py`
- Modify: `backend/src/agent_platform/bootstrap/lifespan.py`
- Modify: `backend/tests/unit/test_settings.py`
- Modify: `backend/tests/integration/test_application_lifespan.py`

- [ ] **Step 1: Write failing watchdog settings tests**

Add `worker_watchdog_interval_seconds: float = 1.0`. Test zero, negative, NaN, and Infinity rejection. Add a model-level test requiring the watchdog interval to be strictly less than the heartbeat timeout.

```python
def test_watchdog_interval_must_be_shorter_than_heartbeat_timeout(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        Settings(
            data_root=tmp_path,
            session_token="local-secret",
            worker_watchdog_interval_seconds=15.0,
            worker_heartbeat_timeout_seconds=15.0,
        )
```

Implement the settings validation as:

```python
worker_heartbeat_timeout_seconds: float = 15.0
worker_watchdog_interval_seconds: float = 1.0

@field_validator(
    "worker_heartbeat_timeout_seconds",
    "worker_watchdog_interval_seconds",
)
@classmethod
def validate_positive_finite_interval(cls, value: float) -> float:
    if not math.isfinite(value) or value <= 0:
        raise ValueError("worker interval must be a positive finite number")
    return value

@model_validator(mode="after")
def watchdog_must_run_before_timeout(self) -> Self:
    if self.worker_watchdog_interval_seconds >= self.worker_heartbeat_timeout_seconds:
        raise ValueError("worker watchdog interval must be shorter than heartbeat timeout")
    return self
```

- [ ] **Step 2: Write failing lifespan watchdog tests**

Use a fake supervisor with `watch_once()` and `stop_all()` events. Cover:

- Watchdog calls `watch_once()` while lifespan is active.
- `app.state.worker_watchdog_task` exists only inside lifespan.
- Shutdown cancels/awaits watchdog before `stop_all()` and database disposal.
- A watchdog failure is retrieved during shutdown, remains the primary cleanup error, still calls `stop_all()` and disposes the database, and does not leak a secret exception message into public state.
- A Watchdog task cancelled before shutdown remains the primary cleanup error instead of being mistaken for the shutdown's own cancellation.
- Startup failure after supervisor creation still stops the supervisor and disposes the database.

RED must show no watchdog task is created.

- [ ] **Step 3: Implement cancellable watchdog ownership**

```python
async def _run_worker_watchdog(
    supervisor: WorkerSupervisor,
    interval_seconds: float,
) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        await supervisor.watch_once()


def _start_worker_watchdog(
    supervisor: WorkerSupervisor,
    interval_seconds: float,
) -> asyncio.Task[None]:
    return asyncio.create_task(
        _run_worker_watchdog(supervisor, interval_seconds)
    )
```

Create the task through `_start_worker_watchdog()` after supervisor construction so startup-failure tests can replace this boundary without monkeypatching global asyncio task creation. Store it in `app.state.worker_watchdog_task`. Extend cleanup to:

```text
cancel and await watchdog
-> stop all workers
-> dispose database
```

Every cleanup step runs even if an earlier one fails. Shutdown suppresses only the cancellation it initiates itself; a task that was already done or already cancelling must report its result as the primary cleanup outcome. Preserve the first error and attach only the existing sanitized secondary-cleanup note for additional failures. `_clear_resource_state()` removes watchdog, supervisor, and database state. Startup cleanup handles partial construction using the same order.

- [ ] **Step 4: Verify GREEN and commit**

```powershell
uv run pytest tests/unit/test_settings.py tests/integration/test_application_lifespan.py tests/process/test_worker_supervisor.py -q
uv run ruff check src tests/unit/test_settings.py tests/integration/test_application_lifespan.py
uv run mypy src
git add backend/src backend/tests/unit/test_settings.py backend/tests/integration/test_application_lifespan.py
git commit -m "feat: run worker watchdog in lifespan"
```

### Task 5: Complete Stage 1D compatibility verification

- [ ] **Step 1: Verify runtime literals and launcher export**

```powershell
uv run python -c "import agent_platform; from importlib.metadata import version; assert agent_platform.__version__ == version('agent-platform-backend'); print(agent_platform.__version__)"
uv run python -c "from agent_platform.main import main, run; print(main.__name__, run.__name__)"
rg -n 'version="0\.1\.0"|EXPECTED_DATABASE_REVISION|uvicorn agent_platform\.bootstrap\.app_factory' src README.md
```

Expected: version and launcher imports succeed; stale-literal search has no matches.

- [ ] **Step 2: Run complete backend gate**

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

- [ ] **Step 3: Review and commit compatibility-only corrections**

Review startup/shutdown ordering, cancellation resistance, error sanitization, loopback enforcement, revision consistency, package version source, public imports, and test coverage. If corrections are required, commit only those corrections as:

```powershell
git add backend/src backend/tests backend/migrations backend/README.md backend/pyproject.toml docs/backend/BACKEND-STAGE1D-RUNTIME-BOOTSTRAP-v1.md
git commit -m "test: verify runtime bootstrap hardening"
```
