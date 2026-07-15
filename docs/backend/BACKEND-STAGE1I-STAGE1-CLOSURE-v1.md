# Backend Stage 1I Stage 1 Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove Stage 1A–1H operate as one compatible runtime, resolve independent-review findings, and mark Stage 1 complete only after migration, security, process, and full quality gates pass.

**Architecture:** Stage 1I adds no new product subsystem. One cross-subsystem integration test exercises durable logging, the instance lock, SQLite maintenance/backup, EventEnvelope persistence, Outbox delivery, and clean restart through the real application lifespan. A traceability document maps every Stage 1 requirement to code and tests; completion status changes only after fresh gates and independent review.

**Tech Stack:** Python 3.12, FastAPI lifespan, SQLAlchemy async, Alembic, SQLite, pytest, Ruff, Mypy, Git.

**Process override:** The user explicitly requested implementation-first testing for Stage 1E–1I. Stage 1I therefore adds its closure test after Stage 1E–1H implementation, then runs focused and complete verification.

**Command convention:** Every command block runs from `D:\AgentProgram\.worktrees\backend-stage1\backend`. Git commands use `git -C ..`.

---

## File map

- Create `backend/tests/integration/test_stage1_runtime_closure.py`: real lifespan, durable event, local audit, backup, redaction, cleanup, and restart proof.
- Create `backend/tests/process/test_logging_fail_stop.py` during Stage 1G: a blocked writer cannot outlive ownership release.
- Create `backend/tests/process/test_outbox_fail_stop.py`: a non-cooperative Dispatcher proves the second shutdown deadline terminates the Backend process without racing later resource cleanup.
- Create `docs/backend/BACKEND-STAGE1-TRACEABILITY-v1.md`: requirement-to-code-to-test matrix for Stage 1A–1I.
- Modify `docs/PROJECT-PLAN.md`: mark Stage 1 complete only after every gate and review passes.
- Modify only Stage 1E–1H files when verification or review proves a compatibility defect.

### Task 1: Add one real cross-subsystem runtime closure test

**Files:**
- Create: `backend/tests/integration/test_stage1_runtime_closure.py`

- [ ] **Step 1: Implement the closure test after Stage 1E–1H code exists**

Use a disposable data root, apply Alembic head, start the real app lifespan, force one verified backup, append one complete event, wait for `local_audit_v1`, and prove the same root can restart after every resource is released.

```python
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
import structlog
from sqlalchemy import select

from agent_platform.bootstrap.app_factory import create_app
from agent_platform.config.settings import Settings
from agent_platform.domain.events import ActorRef, ActorType, EventEnvelope, EventSource
from agent_platform.infrastructure.database.backup import verify_backup
from agent_platform.infrastructure.database.models import LocalAuditEventRow
from agent_platform.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from agent_platform.ports.event_publishing import LOCAL_AUDIT_CONSUMER


def _upgrade_to_head(data_root: Path) -> None:
    backend_root = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    environment["AGENT_PLATFORM_DATA_ROOT"] = str(data_root)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


async def _wait_for_audit(database: object, event_id: int) -> LocalAuditEventRow:
    for _ in range(200):
        async with database.sessions() as session:
            row = await session.scalar(
                select(LocalAuditEventRow).where(
                    LocalAuditEventRow.event_log_id == event_id
                )
            )
        if row is not None:
            return row
        await asyncio.sleep(0.01)
    raise AssertionError("local audit delivery did not complete")


@pytest.mark.asyncio
async def test_stage1_runtime_persists_audits_backups_logs_and_restarts(
    tmp_path: Path,
) -> None:
    session_token = "stage1-closure-secret"
    settings = Settings(
        data_root=tmp_path,
        session_token=session_token,
        worker_heartbeat_timeout_seconds=1.0,
        worker_watchdog_interval_seconds=0.1,
        database_maintenance_interval_seconds=60.0,
        database_integrity_check_interval_seconds=60.0,
        database_backup_interval_seconds=60.0,
        outbox_poll_interval_seconds=0.01,
        outbox_lease_seconds=1.0,
        outbox_publish_timeout_seconds=0.5,
        outbox_shutdown_drain_seconds=1.0,
        outbox_cleanup_interval_seconds=60.0,
    )
    _upgrade_to_head(settings.data_root)
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        database = app.state.database
        await app.state.database_maintenance.run_once(force_backup=True)
        envelope = EventEnvelope(
            schema_version=1,
            event_type="system.stage1_closure",
            correlation_id="stage1_closure_1",
            actor=ActorRef(type=ActorType.SYSTEM),
            source=EventSource.BACKEND,
            occurred_at=datetime.now(UTC),
            payload={"status": "verified"},
        )
        async with SqlAlchemyUnitOfWork(
            database.sessions,
            delivery_targets=(LOCAL_AUDIT_CONSUMER,),
        ) as uow:
            event_id = await uow.events.append(
                envelope=envelope,
                aggregate_type="system",
                aggregate_id="system_stage1",
            )
            await uow.commit()

        audit = await _wait_for_audit(database, event_id)
        assert audit.event_type == envelope.event_type
        structlog.get_logger("stage1-closure").info(
            "closure log",
            embedded_secret=f"Bearer {session_token}",
            event_id=event_id,
        )

    for attribute in (
        "outbox_dispatcher_task",
        "database_maintenance_task",
        "worker_watchdog_task",
        "worker_supervisor",
        "database",
        "logging_runtime",
        "instance_lock",
    ):
        assert not hasattr(app.state, attribute)

    manifests = sorted(settings.backup_root.glob("*.manifest.json"))
    assert manifests
    assert verify_backup(manifests[-1]).manifest.schema_revision is not None
    log_text = (settings.log_root / "backend.jsonl").read_text(encoding="utf-8")
    assert session_token not in log_text
    assert "***" in log_text

    restarted_app = create_app(settings)
    async with restarted_app.router.lifespan_context(restarted_app):
        assert hasattr(restarted_app.state, "instance_lock")
```

If the final frozen interfaces use a narrower static type than `object` for `_wait_for_audit`, import and use that exact type without changing behavior.

- [ ] **Step 2: Run focused closure verification**

```powershell
uv run pytest tests/integration/test_stage1_runtime_closure.py tests/integration/test_application_lifespan.py -q
uv run ruff check tests/integration/test_stage1_runtime_closure.py
uv run mypy src
```

- [ ] **Step 3: Commit**

```powershell
git -C .. add backend/tests/integration/test_stage1_runtime_closure.py
git -C .. commit -m "test: exercise complete stage1 runtime"
```

### Task 2: Run the complete Stage 1 migration and safety matrix

**Files:**
- Modify only files whose Stage 1 implementation is proven defective by these commands.

- [ ] **Step 1: Run migration and database matrix**

```powershell
uv run pytest tests/migration/test_foundation_migration.py tests/migration/test_reliable_outbox_migration.py tests/unit/test_database_instance_lock.py tests/unit/test_database_integrity.py tests/integration/test_database_bootstrap.py tests/integration/test_database_backup.py tests/integration/test_database_maintenance.py -q
```

- [ ] **Step 2: Run diagnostics, IPC, Outbox, and lifecycle matrix**

```powershell
uv run pytest tests/unit/test_redaction.py tests/unit/test_log_redaction.py tests/unit/test_worker_stderr.py tests/unit/test_ipc_replay.py tests/unit/test_ipc_framing.py tests/unit/test_outbox_policy.py tests/unit/test_outbox_dispatcher.py tests/process/test_logging_runtime.py tests/process/test_uvicorn_logging.py tests/process/test_logging_fail_stop.py tests/process/test_worker_protocol.py tests/process/test_worker_supervisor.py tests/process/test_outbox_fail_stop.py tests/integration/test_event_unit_of_work.py tests/integration/test_outbox_store.py tests/integration/test_local_audit_publisher.py tests/integration/test_application_lifespan.py tests/integration/test_stage1_runtime_closure.py tests/contract/test_system_api.py -q
```

- [ ] **Step 3: Run immutable-boundary searches**

```powershell
$repo = 'D:\AgentProgram\.worktrees\backend-stage1'
$backend = Join-Path $repo 'backend'
git -C $repo diff --exit-code 30dcd33 -- backend/migrations/versions/0001_foundation.py

$searches = @(
    @('seen_inbound_message_ids|last_inbound_sequence|EXPECTED_DATABASE_REVISION|version="0\.1\.0"', (Join-Path $backend 'src'), (Join-Path $backend 'tests'), (Join-Path $backend 'README.md')),
    @('copyfile|copy2|agent\.db-wal|agent\.db-shm|DELETE FROM event_log|unlink\(.*event_log', (Join-Path $backend 'src'), (Join-Path $backend 'migrations'))
)
foreach ($search in $searches) {
    $pattern = $search[0]
    $paths = $search[1..($search.Count - 1)]
    $matches = & rg -n $pattern $paths 2>&1
    $status = $LASTEXITCODE
    if ($status -eq 0) {
        $matches
        throw "Forbidden Stage 1 boundary match: $pattern"
    }
    if ($status -ne 1) {
        $matches
        throw "rg failed with exit code $status"
    }
}
```

Expected: foundation revision has no content change; stale/unbounded searches have no production matches; no direct SQLite sidecar copy/delete or EventLog deletion exists.

### Task 3: Create the Stage 1 traceability record

**Files:**
- Create: `docs/backend/BACKEND-STAGE1-TRACEABILITY-v1.md`

- [ ] **Step 1: Write the final matrix**

The document contains these exact requirement rows and points each row to its final implementation and focused tests:

```markdown
# Backend Stage 1 Traceability

| Requirement | Implementation | Verification |
| --- | --- | --- |
| Shared contracts and identifiers | `backend/src/agent_platform/domain/contracts/` | `backend/tests/unit/test_execution_contracts.py` |
| EventEnvelope and error categories | `backend/src/agent_platform/domain/events/`, `domain/shared/errors.py` | `test_event_contracts.py`, `test_domain_shared.py`, `test_system_api.py` |
| RoleCard resources and StageContract | `domain/contracts/`, `resources/roles/v1/` | `test_role_card_resources.py`, `test_stage_role_alignment.py`, `test_stage_contracts.py` |
| Version, schema, launcher, Watchdog | `version.py`, `schema.py`, `main.py`, `bootstrap/lifespan.py` | `test_version.py`, migration tests, `test_main.py`, lifespan tests |
| Durable diagnostics | `infrastructure/redaction.py`, `infrastructure/logging/`, `workers/stderr.py` | redaction/log/stderr/process tests |
| Bounded bidirectional IPC replay | `interfaces/ipc/replay.py`, Backend/Worker integration | replay/framing/protocol/supervisor tests |
| SQLite resilience | `instance_lock.py`, `integrity.py`, `backup.py`, `maintenance.py` | lock/integrity/backup/maintenance tests |
| Durable EventLog and reliable Outbox | event repository, `outbox_store.py`, `local_audit.py`, `outbox_dispatcher.py` | migration/UoW/Outbox/audit/fail-stop tests |
| Complete runtime closure | application lifespan | `test_stage1_runtime_closure.py`, complete backend gate |
```

Add a final section listing the deliberate deferrals: Stage 2 project/workspace/checkpoint features, Stage 3 WebSocket/event replay, Electron token/port control, product Git, and Worker auto-restart.

- [ ] **Step 2: Validate paths and commit**

```powershell
git -C .. ls-files backend/src backend/tests docs/backend | Out-Null
git -C .. add docs/backend/BACKEND-STAGE1-TRACEABILITY-v1.md
git -C .. commit -m "docs: trace backend stage1 completion"
```

### Task 4: Run fresh complete quality gates and independent review

**Files:**
- Modify only files required to resolve verified findings.

- [ ] **Step 1: Run fresh complete gates**

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

Every command must exit `0`. Record the actual pytest pass/skip counts in the final handoff message, not as a hard-coded source comment.

- [ ] **Step 2: Request independent review**

Review the Git range from commit `d9d37c5` through the current Stage 1 HEAD against:

- `docs/PROJECT-PLAN.md` Stage 1 delivery and gate;
- `docs/backend/BACKEND-STAGE1E-1I-REMAINING-HARDENING-DESIGN-v1.md`;
- all five Stage 1E–1I plans.

The reviewer must inspect migrations, Windows lock semantics, secret leakage, symlink/reparse safety, lifecycle cleanup, IPC boundedness, Outbox crash windows, and test realism. Resolve every Critical and Important finding, then rerun all four complete gates.

### Task 5: Mark Stage 1 complete only after verification

**Files:**
- Modify: `docs/PROJECT-PLAN.md`
- Modify: `docs/backend/BACKEND-STAGE1E-1I-REMAINING-HARDENING-DESIGN-v1.md`

- [ ] **Step 1: Update milestone status**

Only after Task 4 passes, change:

```markdown
### 阶段 1：后端共享协议与基础加固
```

to:

```markdown
### 阶段 1：后端共享协议与基础加固（已完成）
```

Change the design status line to:

```markdown
> Status: implemented and independently verified; Stage 2 may begin.
```

- [ ] **Step 2: Run final documentation and worktree checks**

```powershell
rg -n "阶段 1：后端共享协议与基础加固（已完成）|Status: implemented and independently verified" ..\docs
git -C .. diff --check
git -C .. status --short
```

- [ ] **Step 3: Commit Stage 1 closure**

```powershell
git -C .. add docs/PROJECT-PLAN.md docs/backend/BACKEND-STAGE1E-1I-REMAINING-HARDENING-DESIGN-v1.md docs/backend/BACKEND-STAGE1I-STAGE1-CLOSURE-v1.md
git -C .. commit -m "docs: close backend stage1 milestone"
```

Expected final state: the branch is clean, Stage 1 is explicitly complete, Stage 2 remains unimplemented, and the final handoff reports fresh full-gate evidence plus independent-review status.
