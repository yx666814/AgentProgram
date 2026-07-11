# Backend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新建一个可启动、可迁移、可认证、可记录事件并能可靠拉起最小 Project Worker 的 Python 后端骨架。

**Architecture:** 在新 `backend/` 目录实现模块化单体主进程。FastAPI 通过 App Factory 启动，SQLite 由主进程单写，EventLog 与 Outbox 同事务保存；Worker 使用 stdin/stdout 长度帧 IPC，不访问数据库和工具。

**Tech Stack:** Python 3.12, uv, FastAPI, Uvicorn, Pydantic v2, pydantic-settings, SQLAlchemy 2.x, aiosqlite, Alembic, structlog, psutil, pytest, pytest-asyncio, Ruff, mypy.

---

## Scope

本计划只实现基础设施骨架：

- Python package 与开发工具。
- Settings 和应用目录。
- 结构化日志与脱敏。
- SQLite/Alembic 基础。
- EventLog/Outbox/UnitOfWork。
- FastAPI health/readiness 与本地 Bearer Auth。
- 长度帧 Worker IPC。
- 最小 Worker Supervisor、heartbeat、shutdown。

本计划不实现 Project、完整 Workflow、聊天室、模型调用、工具执行、快照和 Quality Gate。这些由后续计划实现。

## File Map

```text
backend/
├─ pyproject.toml
├─ README.md
├─ alembic.ini
├─ migrations/
│  ├─ env.py
│  └─ versions/0001_foundation.py
├─ src/agent_platform/
│  ├─ __init__.py
│  ├─ bootstrap/
│  │  ├─ app_factory.py
│  │  └─ lifespan.py
│  ├─ config/settings.py
│  ├─ domain/shared/
│  │  ├─ errors.py
│  │  └─ ids.py
│  ├─ ports/
│  │  └─ unit_of_work.py
│  ├─ infrastructure/
│  │  ├─ database/
│  │  │  ├─ base.py
│  │  │  ├─ models.py
│  │  │  ├─ session.py
│  │  │  ├─ repositories.py
│  │  │  └─ unit_of_work.py
│  │  ├─ logging/configure.py
│  │  └─ workers/supervisor.py
│  ├─ interfaces/
│  │  ├─ api/
│  │  │  ├─ auth.py
│  │  │  ├─ errors.py
│  │  │  └─ routes/health.py
│  │  └─ ipc/
│  │     ├─ framing.py
│  │     └─ messages.py
│  └─ workers/main.py
└─ tests/
   ├─ unit/
   ├─ integration/
   └─ process/
```

### Task 0: Bootstrap Python Package and Quality Tooling

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/README.md`
- Create: `backend/src/agent_platform/__init__.py`
- Create: `backend/tests/__init__.py`

- [ ] **Step 1: Create the project metadata and locked dependency declaration**

Create `backend/pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "agent-platform-backend"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = [
  "alembic>=1.14,<2",
  "aiosqlite>=0.20,<1",
  "fastapi>=0.115,<1",
  "pydantic>=2.10,<3",
  "pydantic-settings>=2.7,<3",
  "psutil>=6.1,<7",
  "sqlalchemy[asyncio]>=2.0.36,<3",
  "structlog>=24.4,<26",
  "uvicorn[standard]>=0.34,<1",
]

[dependency-groups]
dev = [
  "httpx>=0.28,<1",
  "mypy>=1.14,<2",
  "pytest>=8.3,<9",
  "pytest-asyncio>=0.25,<1",
  "pytest-cov>=6,<7",
  "ruff>=0.9,<1",
]

[tool.hatch.build.targets.wheel]
packages = ["src/agent_platform"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
target-version = "py312"
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "ASYNC"]

[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy", "sqlalchemy.ext.mypy.plugin"]
mypy_path = "src"
```

Create `backend/src/agent_platform/__init__.py`:

```python
"""Contract-driven multi-agent desktop backend."""

__version__ = "0.1.0"
```

Create `backend/README.md`:

```markdown
# Agent Platform Backend

Windows-first local backend for the contract-driven five-stage multi-agent workflow.

## Development

```powershell
uv sync --group dev
uv run pytest
uv run ruff check .
uv run mypy src
```
```

- [ ] **Step 2: Install and lock dependencies**

Run from `backend/`:

```powershell
uv sync --group dev
```

Expected: exit 0 and `backend/uv.lock` created.

- [ ] **Step 3: Verify the package imports**

Run:

```powershell
uv run python -c "import agent_platform; print(agent_platform.__version__)"
```

Expected: `0.1.0`.

- [ ] **Step 4: Verify empty quality gates**

Run:

```powershell
uv run pytest
uv run ruff check .
uv run mypy src
```

Expected: pytest reports no tests collected, Ruff and mypy exit 0.

- [ ] **Step 5: Commit**

```powershell
git add backend/pyproject.toml backend/uv.lock backend/README.md backend/src/agent_platform/__init__.py backend/tests/__init__.py
git commit -m "chore: scaffold backend package"
```

### Task 1: Application Settings and Data Directories

**Files:**
- Create: `backend/src/agent_platform/config/__init__.py`
- Create: `backend/src/agent_platform/config/settings.py`
- Test: `backend/tests/unit/test_settings.py`

- [ ] **Step 1: Write the failing settings tests**

```python
from pathlib import Path

from agent_platform.config.settings import Settings


def test_settings_builds_all_application_directories(tmp_path: Path) -> None:
    settings = Settings(data_root=tmp_path, session_token="secret")

    assert settings.database_path == tmp_path / "data" / "agent.db"
    assert settings.snapshot_root == tmp_path / "snapshots"
    assert settings.log_root == tmp_path / "logs"
    assert settings.backup_root == tmp_path / "backups"
    assert settings.runtime_root == tmp_path / "runtime"


def test_settings_rejects_empty_session_token(tmp_path: Path) -> None:
    try:
        Settings(data_root=tmp_path, session_token="")
    except ValueError as exc:
        assert "session_token" in str(exc)
    else:
        raise AssertionError("empty session token must fail")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
uv run pytest tests/unit/test_settings.py -v
```

Expected: FAIL with `ModuleNotFoundError: agent_platform.config.settings`.

- [ ] **Step 3: Implement Settings**

Create `backend/src/agent_platform/config/settings.py`:

```python
from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_data_root() -> Path:
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "AgentProgram"
    return Path.home() / ".agent-program"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENT_PLATFORM_",
        env_file=None,
        extra="forbid",
    )

    host: str = "127.0.0.1"
    port: int = 0
    data_root: Path = Field(default_factory=default_data_root)
    session_token: str
    log_level: str = "INFO"
    worker_heartbeat_timeout_seconds: float = 15.0

    @field_validator("session_token")
    @classmethod
    def validate_session_token(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("session_token must not be empty")
        return value

    @property
    def database_path(self) -> Path:
        return self.data_root / "data" / "agent.db"

    @property
    def snapshot_root(self) -> Path:
        return self.data_root / "snapshots"

    @property
    def log_root(self) -> Path:
        return self.data_root / "logs"

    @property
    def backup_root(self) -> Path:
        return self.data_root / "backups"

    @property
    def runtime_root(self) -> Path:
        return self.data_root / "runtime"

    def ensure_directories(self) -> None:
        for path in (
            self.database_path.parent,
            self.snapshot_root,
            self.log_root,
            self.backup_root,
            self.runtime_root,
        ):
            path.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: Run the tests**

```powershell
uv run pytest tests/unit/test_settings.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/agent_platform/config backend/tests/unit/test_settings.py
git commit -m "feat: add backend settings"
```

### Task 2: Structured Logging and Secret Redaction

**Files:**
- Create: `backend/src/agent_platform/infrastructure/logging/__init__.py`
- Create: `backend/src/agent_platform/infrastructure/logging/configure.py`
- Test: `backend/tests/unit/test_log_redaction.py`

- [ ] **Step 1: Write the failing redaction test**

```python
from agent_platform.infrastructure.logging.configure import redact_secrets


def test_redact_secrets_masks_nested_credentials() -> None:
    event = {
        "authorization": "Bearer abc",
        "api_key": "sk-secret",
        "nested": {"token": "hidden", "safe": "value"},
    }

    redacted = redact_secrets(None, "info", event)

    assert redacted["authorization"] == "***"
    assert redacted["api_key"] == "***"
    assert redacted["nested"]["token"] == "***"
    assert redacted["nested"]["safe"] == "value"
```

- [ ] **Step 2: Run the test to verify it fails**

```powershell
uv run pytest tests/unit/test_log_redaction.py -v
```

Expected: FAIL because `configure` does not exist.

- [ ] **Step 3: Implement structured logging**

```python
from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import structlog


SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "credential",
    "password",
    "secret",
    "session_token",
    "token",
}


def _redact(value: Any, key: str | None = None) -> Any:
    if key and key.lower() in SENSITIVE_KEYS:
        return "***"
    if isinstance(value, Mapping):
        return {item_key: _redact(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def redact_secrets(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    return _redact(event_dict)


def configure_logging(log_root: Path, level: str) -> None:
    log_root.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=level, format="%(message)s")
    structlog.configure(
        processors=[
            redact_secrets,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        logger_factory=structlog.PrintLoggerFactory(),
    )
```

- [ ] **Step 4: Run tests and static checks**

```powershell
uv run pytest tests/unit/test_log_redaction.py -v
uv run ruff check src/agent_platform/infrastructure/logging tests/unit/test_log_redaction.py
uv run mypy src/agent_platform/infrastructure/logging
```

Expected: all commands exit 0.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/agent_platform/infrastructure/logging backend/tests/unit/test_log_redaction.py
git commit -m "feat: add structured log redaction"
```

### Task 3: Domain IDs and Foundation Errors

**Files:**
- Create: `backend/src/agent_platform/domain/shared/__init__.py`
- Create: `backend/src/agent_platform/domain/shared/ids.py`
- Create: `backend/src/agent_platform/domain/shared/errors.py`
- Test: `backend/tests/unit/test_domain_shared.py`

- [ ] **Step 1: Write the failing domain tests**

```python
from agent_platform.domain.shared.errors import DomainError
from agent_platform.domain.shared.ids import new_id


def test_new_id_contains_prefix_and_unique_suffix() -> None:
    first = new_id("evt")
    second = new_id("evt")

    assert first.startswith("evt_")
    assert first != second


def test_domain_error_exposes_stable_code() -> None:
    error = DomainError(code="workflow.invalid_state", message="invalid")

    assert error.code == "workflow.invalid_state"
    assert str(error) == "invalid"
```

- [ ] **Step 2: Run the tests to verify they fail**

```powershell
uv run pytest tests/unit/test_domain_shared.py -v
```

Expected: FAIL because domain shared modules do not exist.

- [ ] **Step 3: Implement IDs and errors**

Create `ids.py`:

```python
from uuid import uuid4


def new_id(prefix: str) -> str:
    normalized = prefix.strip().lower()
    if not normalized or "_" in normalized:
        raise ValueError("prefix must be a non-empty token without underscores")
    return f"{normalized}_{uuid4().hex}"
```

Create `errors.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(eq=False)
class DomainError(Exception):
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    retryable: bool = False

    def __str__(self) -> str:
        return self.message
```

- [ ] **Step 4: Run tests**

```powershell
uv run pytest tests/unit/test_domain_shared.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/agent_platform/domain/shared backend/tests/unit/test_domain_shared.py
git commit -m "feat: add domain foundation types"
```

### Task 4: Async SQLite, WAL Pragmas and Initial Migration

**Files:**
- Create: `backend/src/agent_platform/infrastructure/database/__init__.py`
- Create: `backend/src/agent_platform/infrastructure/database/base.py`
- Create: `backend/src/agent_platform/infrastructure/database/models.py`
- Create: `backend/src/agent_platform/infrastructure/database/session.py`
- Create: `backend/alembic.ini`
- Create: `backend/migrations/env.py`
- Create: `backend/migrations/versions/0001_foundation.py`
- Modify: `backend/src/agent_platform/config/settings.py`
- Test: `backend/tests/integration/test_database_bootstrap.py`

- [ ] **Step 1: Write the failing SQLite configuration test**

```python
from pathlib import Path

import pytest
from sqlalchemy import text

from agent_platform.infrastructure.database.session import create_database


@pytest.mark.asyncio
async def test_sqlite_uses_wal_foreign_keys_and_busy_timeout(tmp_path: Path) -> None:
    database = create_database(tmp_path / "agent.db")

    async with database.engine.connect() as connection:
        journal_mode = (await connection.execute(text("PRAGMA journal_mode"))).scalar_one()
        foreign_keys = (await connection.execute(text("PRAGMA foreign_keys"))).scalar_one()
        busy_timeout = (await connection.execute(text("PRAGMA busy_timeout"))).scalar_one()
        synchronous = (await connection.execute(text("PRAGMA synchronous"))).scalar_one()
        temp_store = (await connection.execute(text("PRAGMA temp_store"))).scalar_one()

    await database.dispose()

    assert str(journal_mode).lower() == "wal"
    assert foreign_keys == 1
    assert busy_timeout == 5_000
    assert synchronous == 1
    assert temp_store == 2
```

- [ ] **Step 2: Run the test to verify it fails**

Run from `backend/`:

```powershell
uv run pytest tests/integration/test_database_bootstrap.py -v
```

Expected: FAIL because `agent_platform.infrastructure.database.session` does not exist.

- [ ] **Step 3: Implement the database base, foundation rows and engine factory**

Create `base.py`:

```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

Create `models.py`:

```python
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from agent_platform.infrastructure.database.base import Base


class EventLogRow(Base):
    __tablename__ = "event_log"

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    workflow_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    room_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OutboxEventRow(Base):
    __tablename__ = "outbox_events"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    event_log_id: Mapped[int] = mapped_column(
        ForeignKey("event_log.event_id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    delivery_state: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

Create `session.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


@dataclass(frozen=True)
class Database:
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]

    async def dispose(self) -> None:
        await self.engine.dispose()


def _set_sqlite_pragmas(dbapi_connection: object, _: object) -> None:
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA temp_store=MEMORY")
    cursor.close()


def create_database(path: Path) -> Database:
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
    event.listen(engine.sync_engine, "connect", _set_sqlite_pragmas)
    sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return Database(engine=engine, sessions=sessions)
```

Add to `Settings`:

```python
    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.database_path.as_posix()}"
```

- [ ] **Step 4: Add Alembic configuration and the initial migration**

Create `backend/alembic.ini` with `script_location = migrations` and leave `sqlalchemy.url` empty. In `migrations/env.py`, load `AGENT_PLATFORM_DATA_ROOT`, import `Base.metadata`, convert the async URL to `sqlite:///...`, and run migrations through a synchronous connection. Create `0001_foundation.py` with exact `event_log` and `outbox_events` columns from `models.py`, including event context indexes and indexes on `event_type`, `aggregate_id`, `event_log_id`, and `delivery_state`.

The revision header must be:

```python
revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None
```

- [ ] **Step 5: Run migration and integration checks**

```powershell
$env:AGENT_PLATFORM_DATA_ROOT = (Join-Path $PWD '.tmp-foundation')
uv run alembic upgrade head
uv run pytest tests/integration/test_database_bootstrap.py -v
uv run ruff check migrations src/agent_platform/infrastructure/database tests/integration/test_database_bootstrap.py
uv run mypy src/agent_platform/infrastructure/database
```

Expected: migration exits 0, test passes, Ruff and mypy exit 0.

- [ ] **Step 6: Commit**

```powershell
git add backend/alembic.ini backend/migrations backend/src/agent_platform/config/settings.py backend/src/agent_platform/infrastructure/database backend/tests/integration/test_database_bootstrap.py
git commit -m "feat: add async sqlite foundation"
```

### Task 5: Atomic EventLog, Outbox and Unit of Work

**Files:**
- Create: `backend/src/agent_platform/ports/__init__.py`
- Create: `backend/src/agent_platform/ports/unit_of_work.py`
- Create: `backend/src/agent_platform/infrastructure/database/repositories.py`
- Create: `backend/src/agent_platform/infrastructure/database/unit_of_work.py`
- Test: `backend/tests/integration/test_event_unit_of_work.py`

- [ ] **Step 1: Write failing atomicity tests**

```python
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select

from agent_platform.infrastructure.database.base import Base
from agent_platform.infrastructure.database.models import EventLogRow, OutboxEventRow
from agent_platform.infrastructure.database.session import create_database
from agent_platform.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork


@pytest.mark.asyncio
async def test_event_and_outbox_commit_atomically(tmp_path: Path) -> None:
    database = create_database(tmp_path / "agent.db")
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with SqlAlchemyUnitOfWork(database.sessions) as uow:
        event_id = await uow.events.append(
            event_type="workflow.started",
            aggregate_type="workflow",
            aggregate_id="wf_1",
            payload={"mode": "MANUAL"},
            occurred_at=datetime.now(UTC),
        )
        await uow.outbox.enqueue(event_id)
        await uow.commit()

    async with database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(EventLogRow)) == 1
        assert await session.scalar(select(func.count()).select_from(OutboxEventRow)) == 1
    await database.dispose()


@pytest.mark.asyncio
async def test_exception_rolls_back_event_and_outbox(tmp_path: Path) -> None:
    database = create_database(tmp_path / "agent.db")
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    with pytest.raises(RuntimeError):
        async with SqlAlchemyUnitOfWork(database.sessions) as uow:
            event_id = await uow.events.append(
                event_type="workflow.started",
                aggregate_type="workflow",
                aggregate_id="wf_1",
                payload={},
                occurred_at=datetime.now(UTC),
            )
            await uow.outbox.enqueue(event_id)
            raise RuntimeError("abort")

    async with database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(EventLogRow)) == 0
        assert await session.scalar(select(func.count()).select_from(OutboxEventRow)) == 0
    await database.dispose()
```

- [ ] **Step 2: Run tests to verify failure**

```powershell
uv run pytest tests/integration/test_event_unit_of_work.py -v
```

Expected: FAIL because repository and UnitOfWork modules do not exist.

- [ ] **Step 3: Define the UnitOfWork port**

```python
from __future__ import annotations

from datetime import datetime
from types import TracebackType
from typing import Protocol, Self


class EventRepository(Protocol):
    async def append(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, object],
        occurred_at: datetime,
    ) -> int: ...


class OutboxRepository(Protocol):
    async def enqueue(self, event_id: int) -> str: ...


class UnitOfWork(Protocol):
    events: EventRepository
    outbox: OutboxRepository

    async def __aenter__(self) -> Self: ...
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
```

- [ ] **Step 4: Implement repositories and SQLAlchemy UnitOfWork**

`EventLogRepository.append()` adds `EventLogRow`, maps `occurred_at` to `created_at`, calls `flush()`, and returns the database-assigned `event_id`. Extend its signature with optional keyword-only `project_id`, `workflow_id`, `room_id`, and `task_id`, all defaulting to `None`. `OutboxRepository.enqueue()` creates `out_<uuid>` through `new_id("out")` and adds `OutboxEventRow(id=..., event_log_id=event_id, delivery_state="pending", attempt_count=0, created_at=...)`; the WebSocket payload is reconstructed from EventLog, so it is not duplicated in the Outbox row. `SqlAlchemyUnitOfWork` owns one `AsyncSession`, constructs both repositories in `__aenter__`, commits only through `commit()`, and always rolls back uncommitted work in `__aexit__`.

Use this public constructor and fields:

```python
class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None: ...

    session: AsyncSession
    events: EventLogRepository
    outbox: OutboxRepository
```

- [ ] **Step 5: Run tests and checks**

```powershell
uv run pytest tests/integration/test_event_unit_of_work.py -v
uv run ruff check src/agent_platform/ports src/agent_platform/infrastructure/database tests/integration/test_event_unit_of_work.py
uv run mypy src/agent_platform/ports src/agent_platform/infrastructure/database
```

Expected: 2 tests pass and static checks exit 0.

- [ ] **Step 6: Commit**

```powershell
git add backend/src/agent_platform/ports backend/src/agent_platform/infrastructure/database backend/tests/integration/test_event_unit_of_work.py
git commit -m "feat: persist events with transactional outbox"
```

### Task 6: FastAPI Factory, Local Authentication and Stable Errors

**Files:**
- Create: `backend/src/agent_platform/interfaces/api/__init__.py`
- Create: `backend/src/agent_platform/interfaces/api/auth.py`
- Create: `backend/src/agent_platform/interfaces/api/errors.py`
- Create: `backend/src/agent_platform/interfaces/api/routes/__init__.py`
- Create: `backend/src/agent_platform/interfaces/api/routes/health.py`
- Create: `backend/src/agent_platform/bootstrap/app_factory.py`
- Test: `backend/tests/contract/test_system_api.py`

- [ ] **Step 1: Write failing API contract tests**

```python
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from agent_platform.bootstrap.app_factory import create_app
from agent_platform.config.settings import Settings


@pytest.mark.asyncio
async def test_protected_health_requires_exact_bearer_token(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path, session_token="local-secret"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.get("/api/v1/health")
        allowed = await client.get(
            "/api/v1/health",
            headers={"Authorization": "Bearer local-secret"},
        )

    assert denied.status_code == 401
    assert denied.json()["error"]["code"] == "auth.invalid_session"
    assert allowed.status_code == 200
    assert allowed.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readiness_reports_database_state(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path, session_token="local-secret"))
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/readiness",
                headers={"Authorization": "Bearer local-secret"},
            )

    assert response.status_code == 200
    assert response.json()["database"] == "ready"
```

- [ ] **Step 2: Run tests to verify failure**

```powershell
uv run pytest tests/contract/test_system_api.py -v
```

Expected: FAIL because `create_app` does not exist.

- [ ] **Step 3: Implement authentication and error envelopes**

Use `HTTPBearer(auto_error=False)` and `secrets.compare_digest`. The dependency reads `request.app.state.settings.session_token`; missing, wrong-scheme, or wrong-token credentials raise:

```python
HTTPException(
    status_code=401,
    detail={"code": "auth.invalid_session", "message": "Invalid local session"},
)
```

Register handlers that always return:

```json
{"error":{"code":"auth.invalid_session","message":"Invalid local session","details":{},"retryable":false}}
```

`DomainError` maps to 409 by default; request validation maps to `request.validation_failed` with status 422; unhandled exceptions map to `internal.error` with status 500 and never include exception text.

- [ ] **Step 4: Implement routes and App Factory**

`GET /api/v1/health` returns `{"status": "ok"}`. `GET /api/v1/readiness` runs `SELECT 1` through `app.state.database.engine` and returns `{"status":"ready","database":"ready"}`. Both require local Bearer auth.

`create_app(settings)` must:

```python
def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="Agent Platform Backend", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.include_router(health_router, prefix="/api/v1", dependencies=[Depends(require_session)])
    register_error_handlers(app)
    return app
```

The initial `lifespan` ensures directories, creates `Database`, creates `Base.metadata` during tests/development, stores it on `app.state.database`, yields, then disposes it. Alembic remains the production schema path.

- [ ] **Step 5: Run API tests and schema check**

```powershell
uv run pytest tests/contract/test_system_api.py -v
uv run python -c "from agent_platform.bootstrap.app_factory import create_app; from agent_platform.config.settings import Settings; print(create_app(Settings(session_token='x')).openapi()['info']['version'])"
```

Expected: 2 tests pass and schema prints `0.1.0`.

- [ ] **Step 6: Commit**

```powershell
git add backend/src/agent_platform/bootstrap backend/src/agent_platform/interfaces/api backend/tests/contract/test_system_api.py
git commit -m "feat: expose authenticated system api"
```

### Task 7: Versioned Length-Framed IPC

**Files:**
- Create: `backend/src/agent_platform/interfaces/ipc/__init__.py`
- Create: `backend/src/agent_platform/interfaces/ipc/messages.py`
- Create: `backend/src/agent_platform/interfaces/ipc/framing.py`
- Test: `backend/tests/unit/test_ipc_framing.py`

- [ ] **Step 1: Write failing framing tests**

```python
from agent_platform.interfaces.ipc.framing import FrameDecoder, encode_frame
from agent_platform.interfaces.ipc.messages import IpcMessage


def test_decoder_handles_partial_unicode_frame() -> None:
    message = IpcMessage(
        message_id="msg_1",
        correlation_id=None,
        sequence=7,
        project_id="project_1",
        task_id="task_1",
        type="event",
        payload={"text": "你好\nworker"},
    )
    encoded = encode_frame(message)
    decoder = FrameDecoder()

    result = []
    for byte in encoded:
        result.extend(decoder.feed(bytes([byte])))

    assert result == [message]


def test_decoder_reads_two_frames_from_one_chunk() -> None:
    first = IpcMessage(message_id="m1", sequence=1, project_id="p", type="heartbeat")
    second = IpcMessage(message_id="m2", sequence=2, project_id="p", type="ack")

    assert FrameDecoder().feed(encode_frame(first) + encode_frame(second)) == [first, second]
```

- [ ] **Step 2: Run tests to verify failure**

```powershell
uv run pytest tests/unit/test_ipc_framing.py -v
```

Expected: FAIL because IPC modules do not exist.

- [ ] **Step 3: Implement versioned messages**

```python
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


MessageType = Literal["command", "response", "event", "ack", "heartbeat", "cancel", "shutdown"]


class IpcMessage(BaseModel):
    protocol_version: int = 1
    message_id: str
    correlation_id: str | None = None
    sequence: int = Field(ge=0)
    project_id: str
    task_id: str | None = None
    type: MessageType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 4: Implement strict Content-Length framing**

`encode_frame()` serializes `model_dump_json()` as UTF-8 bytes and emits exactly:

```text
Content-Length: <byte-count>\r\nProtocol-Version: 1\r\n\r\n<payload>
```

`FrameDecoder.feed(chunk)` buffers bytes, accepts partial headers and bodies, rejects headers larger than 8 KiB, rejects bodies larger than 1 MiB, requires both headers, rejects unsupported protocol versions, and validates every body through `IpcMessage.model_validate_json`. After returning a frame it continues parsing remaining buffered bytes.

Expose these errors:

```python
class FramingError(ValueError):
    pass


MAX_HEADER_BYTES = 8 * 1024
MAX_BODY_BYTES = 1024 * 1024
```

- [ ] **Step 5: Run framing tests and checks**

```powershell
uv run pytest tests/unit/test_ipc_framing.py -v
uv run ruff check src/agent_platform/interfaces/ipc tests/unit/test_ipc_framing.py
uv run mypy src/agent_platform/interfaces/ipc
```

Expected: 2 tests pass and static checks exit 0.

- [ ] **Step 6: Commit**

```powershell
git add backend/src/agent_platform/interfaces/ipc backend/tests/unit/test_ipc_framing.py
git commit -m "feat: add worker ipc framing"
```

### Task 8: Minimal Worker Protocol Loop

**Files:**
- Create: `backend/src/agent_platform/workers/__init__.py`
- Create: `backend/src/agent_platform/workers/main.py`
- Test: `backend/tests/process/test_worker_protocol.py`

- [ ] **Step 1: Write the failing worker process test**

```python
import asyncio
import sys

import pytest

from agent_platform.interfaces.ipc.framing import FrameDecoder, encode_frame
from agent_platform.interfaces.ipc.messages import IpcMessage


@pytest.mark.asyncio
async def test_worker_acknowledges_ping_and_shuts_down() -> None:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "agent_platform.workers.main",
        "--project-id",
        "project_1",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert process.stdin is not None
    assert process.stdout is not None

    process.stdin.write(encode_frame(IpcMessage(
        message_id="cmd_1", sequence=1, project_id="project_1", type="command", payload={"name": "ping"}
    )))
    process.stdin.write(encode_frame(IpcMessage(
        message_id="cmd_2", sequence=2, project_id="project_1", type="shutdown"
    )))
    await process.stdin.drain()

    decoder = FrameDecoder()
    messages = []
    while len(messages) < 2:
        messages.extend(decoder.feed(await asyncio.wait_for(process.stdout.read(4096), 5)))

    assert messages[0].type == "ack"
    assert messages[0].correlation_id == "cmd_1"
    assert messages[-1].type == "response"
    assert messages[-1].payload["status"] == "shutdown_complete"
    assert await asyncio.wait_for(process.wait(), 5) == 0
```

- [ ] **Step 2: Run the test to verify failure**

```powershell
uv run pytest tests/process/test_worker_protocol.py -v
```

Expected: FAIL because the worker module is missing.

- [ ] **Step 3: Implement the worker protocol loop**

`main.py` parses `--project-id`, reserves stdout exclusively for framed messages, sends logs to stderr, and uses one monotonically increasing outbound sequence. It reads stdin in `asyncio.to_thread(sys.stdin.buffer.read1, 65536)`, feeds `FrameDecoder`, and implements:

- `command/ping` → `ack` with matching `correlation_id`.
- `cancel` → `ack` with `payload.status="cancelled"`.
- `shutdown` → `response` with `payload.status="shutdown_complete"`, flush stdout, exit 0.
- a heartbeat task every 5 seconds with `worker_id`, `active_task`, and `last_sequence`.

All stdout writes are protected by one `asyncio.Lock` and performed by `asyncio.to_thread`; EOF exits cleanly. Invalid frames are logged to stderr and exit with code 2.

- [ ] **Step 4: Run process tests**

```powershell
uv run pytest tests/process/test_worker_protocol.py -v
```

Expected: 1 test passes with no protocol text on stderr.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/agent_platform/workers backend/tests/process/test_worker_protocol.py
git commit -m "feat: add minimal project worker"
```

### Task 9: Worker Supervisor, Timeout and Process-Tree Cleanup

**Files:**
- Create: `backend/src/agent_platform/infrastructure/workers/__init__.py`
- Create: `backend/src/agent_platform/infrastructure/workers/supervisor.py`
- Test: `backend/tests/process/test_worker_supervisor.py`

- [ ] **Step 1: Write failing supervisor tests**

```python
from datetime import timedelta

import pytest

from agent_platform.infrastructure.workers.supervisor import WorkerSupervisor


@pytest.mark.asyncio
async def test_supervisor_starts_pings_and_stops_worker() -> None:
    supervisor = WorkerSupervisor(heartbeat_timeout=timedelta(seconds=5))
    handle = await supervisor.start(project_id="project_1")

    reply = await supervisor.ping(handle.worker_id)
    assert reply.type == "ack"
    assert handle.process.returncode is None

    await supervisor.stop(handle.worker_id)
    assert handle.process.returncode == 0


@pytest.mark.asyncio
async def test_force_stop_removes_worker_from_registry() -> None:
    supervisor = WorkerSupervisor(heartbeat_timeout=timedelta(milliseconds=50))
    handle = await supervisor.start(project_id="project_1", worker_module="tests.fixtures.silent_worker")

    await supervisor.watch_once()

    assert supervisor.get(handle.worker_id) is None
    assert handle.process.returncode is not None
```

Create `backend/tests/fixtures/silent_worker.py` as a process that reads stdin forever without heartbeat, and include it in the test file list.

- [ ] **Step 2: Run tests to verify failure**

```powershell
uv run pytest tests/process/test_worker_supervisor.py -v
```

Expected: FAIL because `WorkerSupervisor` does not exist.

- [ ] **Step 3: Implement the supervisor**

Define:

```python
@dataclass
class WorkerHandle:
    worker_id: str
    project_id: str
    process: asyncio.subprocess.Process
    decoder: FrameDecoder
    outbound_sequence: int
    last_heartbeat_at: datetime
    pending: dict[str, asyncio.Future[IpcMessage]]
    reader_task: asyncio.Task[None]


class WorkerSupervisor:
    async def start(self, project_id: str, worker_module: str = "agent_platform.workers.main") -> WorkerHandle: ...
    async def ping(self, worker_id: str) -> IpcMessage: ...
    async def send(self, worker_id: str, message_type: MessageType, payload: dict[str, object]) -> IpcMessage: ...
    async def stop(self, worker_id: str) -> None: ...
    async def stop_all(self) -> None: ...
    async def watch_once(self) -> None: ...
    def get(self, worker_id: str) -> WorkerHandle | None: ...
```

Start workers with `sys.executable -m <worker_module> --project-id <id>` and stdin/stdout/stderr pipes. The reader task resolves correlated futures, updates heartbeat time, and never treats an unacknowledged completion as persisted. `stop()` sends shutdown, waits 3 seconds, then calls a Windows-safe `_terminate_process_tree(pid)` implemented through `psutil.Process(pid).children(recursive=True)` followed by terminate/wait/kill. Always remove the handle and cancel reader/stderr tasks.

- [ ] **Step 4: Run supervisor tests**

```powershell
uv run pytest tests/process/test_worker_supervisor.py -v
uv run ruff check src/agent_platform/infrastructure/workers tests/process tests/fixtures
uv run mypy src/agent_platform/infrastructure/workers
```

Expected: 2 tests pass and no child process remains.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/agent_platform/infrastructure/workers backend/tests/process/test_worker_supervisor.py backend/tests/fixtures/silent_worker.py
git commit -m "feat: supervise project worker lifecycle"
```

### Task 10: Application Lifespan and Graceful Shutdown

**Files:**
- Create: `backend/src/agent_platform/bootstrap/lifespan.py`
- Modify: `backend/src/agent_platform/bootstrap/app_factory.py`
- Modify: `backend/src/agent_platform/interfaces/api/routes/health.py`
- Test: `backend/tests/integration/test_application_lifespan.py`

- [ ] **Step 1: Write the failing lifespan test**

```python
from pathlib import Path

import pytest

from agent_platform.bootstrap.app_factory import create_app
from agent_platform.config.settings import Settings


@pytest.mark.asyncio
async def test_lifespan_initializes_and_closes_runtime(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path, session_token="secret"))

    async with app.router.lifespan_context(app):
        assert app.state.database is not None
        assert app.state.worker_supervisor is not None
        handle = await app.state.worker_supervisor.start("project_1")
        assert handle.process.returncode is None

    assert handle.process.returncode is not None
```

- [ ] **Step 2: Run test to verify failure**

```powershell
uv run pytest tests/integration/test_application_lifespan.py -v
```

Expected: FAIL because the shared lifespan does not install a supervisor.

- [ ] **Step 3: Implement the production lifespan**

Create an `@asynccontextmanager` lifespan that:

1. calls `settings.ensure_directories()`;
2. configures logging;
3. creates the database and verifies `SELECT 1`;
4. creates `WorkerSupervisor` using the configured heartbeat timeout;
5. stores both on `app.state`;
6. yields;
7. stops all workers;
8. disposes the database even when shutdown raises.

Update `create_app()` to bind this lifespan through `build_lifespan(settings)`. Add `GET /api/v1/system/info` returning backend and protocol versions. Production startup must not call `Base.metadata.create_all`; tests apply Alembic or construct tables explicitly.

- [ ] **Step 4: Run application smoke tests**

```powershell
uv run pytest tests/contract/test_system_api.py tests/integration/test_application_lifespan.py -v
uv run python -c "from agent_platform.bootstrap.app_factory import create_app; from agent_platform.config.settings import Settings; app=create_app(Settings(session_token='x')); print(app.title)"
```

Expected: all tests pass and command prints `Agent Platform Backend`.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/agent_platform/bootstrap backend/src/agent_platform/interfaces/api/routes/health.py backend/tests/integration/test_application_lifespan.py
git commit -m "feat: manage backend application lifespan"
```

### Task 11: Foundation Verification and Developer Handoff

**Files:**
- Modify: `backend/README.md`
- Create: `backend/tests/migration/test_foundation_migration.py`

- [ ] **Step 1: Add the migration smoke test**

The test creates a temporary `AGENT_PLATFORM_DATA_ROOT`, runs `alembic upgrade head` in a subprocess, opens SQLite, and asserts the exact table set includes `alembic_version`, `event_log`, and `outbox_events`. It then runs `alembic downgrade base` and asserts only SQLite internal tables remain.

- [ ] **Step 2: Document exact developer commands**

Extend `backend/README.md` with:

- Windows Python 3.12 and `uv` prerequisites.
- `uv sync --group dev`.
- environment variables `AGENT_PLATFORM_SESSION_TOKEN` and `AGENT_PLATFORM_DATA_ROOT`.
- `uv run alembic upgrade head`.
- `uv run uvicorn agent_platform.bootstrap.app_factory:create_app --factory` only through a small documented `dev_app()` factory that supplies settings from environment.
- test, Ruff, format-check and mypy commands.
- statement that Worker stdout is protocol-only and logs use stderr.

- [ ] **Step 3: Run the complete foundation verification**

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest tests/unit tests/integration tests/contract tests/process tests/migration -v
```

Expected: every command exits 0; no skipped foundation test; no orphan `agent_platform.workers.main` process.

- [ ] **Step 4: Inspect tracked secrets and protocol output**

```powershell
rg -n "sk-[A-Za-z0-9]|Bearer +[A-Za-z0-9_-]{12,}|api[_-]?key\s*=" backend -g '!uv.lock'
git diff --check
```

Expected: secret scan has no real credential match and `git diff --check` exits 0.

- [ ] **Step 5: Commit**

```powershell
git add backend/README.md backend/tests/migration/test_foundation_migration.py
git commit -m "test: verify backend foundation"
```

## Definition of Done

- FastAPI binds only the configured loopback host and rejects missing local session authentication.
- SQLite is WAL-enabled with foreign keys and a finite busy timeout.
- EventLog and Outbox commit or roll back together.
- IPC survives partial reads, Unicode, multiple frames and clean shutdown.
- Worker timeout or backend shutdown cleans the complete process tree.
- No Project, Workflow, model, tool, snapshot or Gate business behavior leaks into this foundation plan.
