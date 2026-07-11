# Recovery, Desktop Contract and E2E Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成崩溃恢复、真实 Pause/Resume/Stop/Abandon、Electron Sidecar 控制协议、数据库升级保护、PyInstaller onedir 和 Windows 五阶段 E2E。

**Architecture:** 启动时先恢复数据库与遗留运行状态，再对外 ready。Electron Main 通过继承 stdio 的长度帧 Control Channel 管理 ready、shutdown 和 SecretStore；Renderer 只使用 Preload 窄接口。安装包携带固定 Python 运行时。

**Tech Stack:** Python 3.12, FastAPI, SQLite Backup API, Alembic, psutil, framed IPC, PyInstaller onedir, pytest, Windows process tests.

---

## File Map

```text
backend/src/agent_platform/
├─ application/recovery/{startup.py,workflow_control.py,outbox_recovery.py,database_recovery.py}
├─ application/system/{shutdown.py,diagnostics.py}
├─ ports/desktop_control.py
├─ infrastructure/desktop/{control_channel.py,parent_monitor.py,secret_store_client.py}
├─ infrastructure/database/{backup.py,migration.py}
├─ bootstrap/{sidecar_main.py,ready.py}
└─ packaging/agent-platform-backend.spec
```

### Task 1: Startup Recovery of Workers, Tasks and Outbox

**Files:**
- Create: `backend/src/agent_platform/application/recovery/startup.py`
- Create: `backend/src/agent_platform/application/recovery/outbox_recovery.py`
- Test: `backend/tests/integration/test_startup_recovery.py`

- [ ] **Step 1: Write failing orphan recovery test**

```python
@pytest.mark.asyncio
async def test_startup_marks_orphan_runtime_interrupted(recovery: StartupRecovery) -> None:
    await seed_running_worker_task(worker_pid=999999, last_ack_sequence=8)
    result = await recovery.run()
    assert result.interrupted_tasks == ["task_1"]
    assert (await task_repository.get("task_1")).state is TaskState.INTERRUPTED
    assert (await worker_repository.get("worker_1")).state is WorkerState.INTERRUPTED
    assert event_repository.last().event_type == "worker.interrupted"
```

- [ ] **Step 2: Implement ordered startup audit**

Run: schema/version check → database integrity → detect nonexistent PID leases → mark legacy running Worker/Task/Stage as interrupted → remove incomplete snapshot temp files → restore undelivered Outbox → hash workspace changes → list recoverable projects. Do not automatically restart models, tools or workflows.

- [ ] **Step 3: Make ACK the completion boundary**

Only IPC messages with persisted event id are authoritative. Any Worker completion after last ACK is ignored. Recovery records last confirmed sequence and a new retry creates a new Worker and Task attempt.

- [ ] **Step 4: Verify and commit**

```powershell
uv run pytest tests/integration/test_startup_recovery.py -v
git add backend/src/agent_platform/application/recovery backend/tests/integration/test_startup_recovery.py
git commit -m "feat: recover interrupted backend state"
```

### Task 2: Real Pause, Resume, Stop and Abandon

**Files:**
- Create: `backend/src/agent_platform/application/recovery/workflow_control.py`
- Test: `backend/tests/process/test_workflow_control.py`

- [ ] **Step 1: Write failing Pause process test**

```python
@pytest.mark.asyncio
async def test_pause_cancels_model_tool_and_worker(control: WorkflowControl, running_fixture) -> None:
    result = await control.pause("wf_1", idempotency_key="pause-1")
    assert result.state is WorkflowState.PAUSED
    assert running_fixture.model.cancelled
    assert running_fixture.tool_process.returncode is not None
    assert running_fixture.task.state in {TaskState.CANCELLED, TaskState.INTERRUPTED}
```

- [ ] **Step 2: Implement pause sequence**

Set internal `pause_requested`, stop scheduling, send Worker cancel, cancel pending provider request and Main ToolCall, kill process tree, persist confirmed messages/tool records/interruption point, then enter paused. A failure before final state remains interrupted, never cosmetically paused.

- [ ] **Step 3: Implement resume preconditions**

Revalidate workspace, hashes/external changes, conflicts, handoff/checkpoint, ModelProfiles and contracts; create a new Worker. Resume starts from last database-consistent task boundary and never continues half a model stream or half a ToolCall.

- [ ] **Step 4: Implement stop/abandon**

Stop cancels active work and preserves ability to explicitly restart/copy. Abandon preserves files, chats, artifacts and checkpoints but permanently forbids continuing that Workflow ID. Direct Workspace is never deleted.

- [ ] **Step 5: Verify and commit**

```powershell
uv run pytest tests/process/test_workflow_control.py -v
git add backend/src/agent_platform/application/recovery/workflow_control.py backend/tests/process/test_workflow_control.py
git commit -m "feat: control workflow processes safely"
```

### Task 3: Tool Crash and Partial-Write Recovery

**Files:**
- Create: `backend/src/agent_platform/application/recovery/tool_recovery.py`
- Test: `backend/tests/process/test_tool_crash_recovery.py`

- [ ] **Step 1: Write failing partial-write test**

Start a fixture command that changes one file, creates another, then exits abnormally. Assert ToolCall failed, before/after hashes and stderr are recorded, Task is not completed, and workspace enters inspection/needs-fix instead of reporting success.

- [ ] **Step 2: Implement recovery classification**

Atomic file tools expose no half-file. For external commands compare pre-command checkpoint/planned paths to current hashes. If unexpected writes exist, create ExternalChangeRecord owned by current stage and require Gate rerun; if same-file external edit overlaps, create FileConflict. Never roll back user files automatically.

- [ ] **Step 3: Verify and commit**

```powershell
uv run pytest tests/process/test_tool_crash_recovery.py -v
git add backend/src/agent_platform/application/recovery/tool_recovery.py backend/tests/process/test_tool_crash_recovery.py
git commit -m "feat: recover failed tool writes"
```

### Task 4: SQLite Backup, Migration and Recovery Mode

**Files:**
- Create: `backend/src/agent_platform/infrastructure/database/backup.py`
- Create: `backend/src/agent_platform/infrastructure/database/migration.py`
- Create: `backend/src/agent_platform/application/recovery/database_recovery.py`
- Test: `backend/tests/migration/test_upgrade_recovery.py`

- [ ] **Step 1: Write migration failure restore test**

```python
def test_failed_migration_restores_versioned_backup(tmp_path: Path) -> None:
    database = create_old_database(tmp_path / "agent.db")
    result = upgrade_database(database, failing_migration_runner)
    assert result.mode == "recovery"
    assert sqlite_value(database, "select value from marker") == "before"
    assert result.backup_path.exists()
```

- [ ] **Step 2: Implement protected upgrade**

Stop Workers, use SQLite Backup API to `backups/agent-<schema>-<timestamp>.db`, fsync it, run Alembic, then `PRAGMA foreign_key_check` and `PRAGMA integrity_check`. On any failure close connections, restore backup atomically, enter recovery mode and reject Agent execution. Never migrate a database failing initial integrity check.

- [ ] **Step 3: Add startup recovery API state**

Readiness returns 503 with `system.recovery_required`; system info reports database version and backup location without exposing project/chat content.

- [ ] **Step 4: Verify and commit**

```powershell
uv run pytest tests/migration/test_upgrade_recovery.py -v
git add backend/src/agent_platform/infrastructure/database/backup.py backend/src/agent_platform/infrastructure/database/migration.py backend/src/agent_platform/application/recovery/database_recovery.py backend/tests/migration/test_upgrade_recovery.py
git commit -m "feat: protect desktop database upgrades"
```

### Task 5: Electron Control Channel and Ready Handshake

**Files:**
- Create: `backend/src/agent_platform/ports/desktop_control.py`
- Create: `backend/src/agent_platform/infrastructure/desktop/control_channel.py`
- Create: `backend/src/agent_platform/bootstrap/ready.py`
- Create: `backend/src/agent_platform/bootstrap/sidecar_main.py`
- Test: `backend/tests/process/test_sidecar_ready.py`

- [ ] **Step 1: Write failing sidecar handshake test**

```python
@pytest.mark.asyncio
async def test_sidecar_binds_loopback_dynamic_port_and_emits_one_ready_frame() -> None:
    sidecar = await launch_sidecar(session_token="secret", port=0, parent_pid=os.getpid())
    ready = await sidecar.read_control_frame()
    assert ready.type == "ready"
    assert ready.payload["ready"] is True
    assert ready.payload["port"] > 0
    assert ready.payload["host"] == "127.0.0.1"
    assert await sidecar.stderr_contains_protocol_header() is False
    await sidecar.shutdown()
```

- [ ] **Step 2: Define control messages**

Use the same Content-Length framing but a separate inherited stdio handle. Ready payload includes protocol version, backend version, pid, port, session id, database version and ready. Commands: `shutdown`, `secret.get`, `secret.put`, `secret.delete`; responses always correlate. Backend logs go stderr/file and never stdout/control.

- [ ] **Step 3: Implement sidecar startup**

Parse protected startup config containing loopback host, port 0, session token, session id, parent pid and application data root. Start Uvicorn on an already-selected loopback socket, complete migrations/recovery/lifespan, then write exactly one ready frame. Delete the startup config after reading.

- [ ] **Step 4: Verify and commit**

```powershell
uv run pytest tests/process/test_sidecar_ready.py -v
git add backend/src/agent_platform/ports/desktop_control.py backend/src/agent_platform/infrastructure/desktop/control_channel.py backend/src/agent_platform/bootstrap/ready.py backend/src/agent_platform/bootstrap/sidecar_main.py backend/tests/process/test_sidecar_ready.py
git commit -m "feat: expose desktop sidecar control channel"
```

### Task 6: SecretStore Control Bridge and Session Isolation

**Files:**
- Create: `backend/src/agent_platform/infrastructure/desktop/secret_store_client.py`
- Test: `backend/tests/process/test_secret_store_bridge.py`

- [ ] **Step 1: Write failing isolation test**

Fake Electron control server accepts session A. Assert backend can get `cred_1` only with A, session B is rejected, Renderer-facing API never returns secret, and control/audit logs contain `credential_ref` plus masked hint but not value.

- [ ] **Step 2: Implement bridge**

`DesktopSecretStore` implements SecretStore by correlated control messages. It validates current session id, uses a 10-second timeout, returns bytes only to EphemeralSecret, and treats channel close as `secret_store.unavailable`. It never falls back to plaintext file/database/environment storage.

- [ ] **Step 3: Verify and commit**

```powershell
uv run pytest tests/process/test_secret_store_bridge.py -v
git add backend/src/agent_platform/infrastructure/desktop/secret_store_client.py backend/tests/process/test_secret_store_bridge.py
git commit -m "feat: bridge desktop secure storage"
```

### Task 7: Parent Process Monitoring and Graceful Shutdown API

**Files:**
- Create: `backend/src/agent_platform/infrastructure/desktop/parent_monitor.py`
- Create: `backend/src/agent_platform/application/system/shutdown.py`
- Create: `backend/src/agent_platform/interfaces/api/routes/system.py`
- Test: `backend/tests/process/test_parent_shutdown.py`

- [ ] **Step 1: Write shutdown tests**

Assert `/api/v1/system/shutdown` stops accepting new tasks, cancels model/tool, stops Worker/process trees, drains already-committed Outbox, closes DB and replies `shutdown_complete`. Simulate parent PID disappearance and assert the same safe shutdown occurs without killing unrelated Python processes.

- [ ] **Step 2: Implement parent identity checks**

Monitor exact PID plus captured creation time and session id every two seconds. PID reuse or missing parent triggers shutdown. Never enumerate and kill by process name. Shutdown has bounded phases; if a phase times out, record it and continue cleanup, leaving startup recovery evidence.

- [ ] **Step 3: Verify and commit**

```powershell
uv run pytest tests/process/test_parent_shutdown.py -v
git add backend/src/agent_platform/infrastructure/desktop/parent_monitor.py backend/src/agent_platform/application/system/shutdown.py backend/src/agent_platform/interfaces/api/routes/system.py backend/tests/process/test_parent_shutdown.py
git commit -m "feat: shut down desktop process tree"
```

### Task 8: Redacted Diagnostics Bundle

**Files:**
- Create: `backend/src/agent_platform/application/system/diagnostics.py`
- Test: `backend/tests/security/test_diagnostics_bundle.py`

- [ ] **Step 1: Write exclusion tests**

Create fixtures containing API key, full chat, project source and environment secrets. Default bundle must contain version, OS, DB health summary, recent redacted structured logs, crash ids and migration state, but none of the fixture secrets/content. Explicit optional paths are still normalized and individually confirmed by caller input.

- [ ] **Step 2: Implement safe ZIP export**

Generate under runtime diagnostics with random name; redact structured fields and secret-like strings; do not follow links; exclude project/chat/snapshot/database by default; write manifest listing included categories and hashes. API returns a one-time local reference, not arbitrary filesystem access.

- [ ] **Step 3: Verify and commit**

```powershell
uv run pytest tests/security/test_diagnostics_bundle.py -v
git add backend/src/agent_platform/application/system/diagnostics.py backend/tests/security/test_diagnostics_bundle.py
git commit -m "feat: export redacted diagnostics"
```

### Task 9: PyInstaller `onedir` Sidecar Package

**Files:**
- Create: `backend/packaging/agent-platform-backend.spec`
- Create: `backend/packaging/hooks/hook-agent_platform.py`
- Modify: `backend/pyproject.toml`
- Modify: `backend/README.md`
- Test: `backend/tests/packaging/test_packaged_sidecar.py`

- [ ] **Step 1: Add packaging dependency and spec**

Add PyInstaller to a `packaging` dependency group. Spec uses `onedir`, console disabled for release, entry `sidecar_main.py`, includes Alembic migrations, StageContract JSON, role-card resources and necessary provider/watchfiles/zstandard modules. Runtime resource access uses `importlib.resources`, never source-relative paths.

- [ ] **Step 2: Build and run packaged smoke test**

```powershell
uv sync --group dev --group packaging
uv run pyinstaller --noconfirm packaging/agent-platform-backend.spec
uv run pytest tests/packaging/test_packaged_sidecar.py -v
```

Test launches from a path containing spaces and Chinese characters, with PATH excluding Python, reads ready, calls health/readiness, starts/stops a Worker, and shuts down with no descendants.

- [ ] **Step 3: Document Electron packaging contract and commit**

Document executable directory layout, startup config, control handles, dynamic port, token lifecycle, update backup sequence and required Electron safeStorage behavior.

```powershell
git add backend/packaging backend/pyproject.toml backend/uv.lock backend/README.md backend/tests/packaging/test_packaged_sidecar.py
git commit -m "build: package backend desktop sidecar"
```

### Task 10: Complete Windows Fake-Model E2E Matrix

**Files:**
- Create: `backend/tests/e2e/fixtures/fullstack_project.py`
- Create: `backend/tests/e2e/test_manual_workflow.py`
- Create: `backend/tests/e2e/test_autonomous_workflow.py`
- Create: `backend/tests/e2e/test_existing_project_preflight.py`
- Create: `backend/tests/e2e/test_change_request_and_conflict.py`
- Create: `backend/tests/e2e/test_restart_recovery.py`

- [ ] **Step 1: Build the deterministic sample project fixture**

Fixture contains a minimal frontend, backend, tests, manifest and scripted Fake Model outputs for five roles. Builder writes both frontend/backend and tests; Reviewer runs independent commands; Deployer writes docs/config only and makes no verification/deploy call.

- [ ] **Step 2: Implement required scenarios**

Manual: five approvals plus CapabilityRequest. Autonomous: PASS auto-handoff, Warning waits for rewrite/open_room/abandon, no stage approval, CapabilityRequest still waits. Existing: healthy passes, no tests passes with Builder test task, failing build/test rejects. ChangeRequest: Reviewer routes design defect to Designer and invalidates downstream. Conflict: user/Builder same file creates three-way resolution. Restart: force close during model task, restart shows interrupted with intact chat/checkpoint.

- [ ] **Step 3: Run complete backend acceptance**

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest tests/unit -v
uv run pytest tests/integration -v
uv run pytest tests/contract -v
uv run pytest tests/security -v
uv run pytest tests/process tests/migration tests/packaging -v
uv run pytest tests/e2e -v
```

Expected: all suites pass on Windows 10/11 runner; no real model/API key/network deployment is required.

- [ ] **Step 4: Run final secret and orphan-process checks**

```powershell
rg -n "sk-[A-Za-z0-9]|Authorization: Bearer [^<]|api[_-]?key\s*[:=]\s*['\"]" backend -g '!uv.lock'
Get-Process | Where-Object { $_.Path -like '*agent-platform-backend*' -or $_.CommandLine -like '*agent_platform.workers.main*' }
git diff --check
```

Expected: no real secret match, no orphan backend/Worker, clean diff whitespace.

- [ ] **Step 5: Commit**

```powershell
git add backend/tests/e2e
git commit -m "test: verify complete desktop backend workflow"
```

## Definition of Done

- 崩溃、Pause 和退出真实停止模型、工具、Worker 与后代进程，不制造虚假完成。
- 桌面升级前自动备份；迁移或 integrity 失败恢复备份并进入恢复模式。
- 后端只绑定 loopback 动态端口，Ready/Control 不被日志污染，Renderer 不接触 Token/API Key。
- 安装包使用 `onedir` 自带 Python 3.12，路径含空格/中文且系统无 Python 时仍能运行。
- MANUAL、AUTONOMOUS、ChangeRequest、ExternalConflict、Restart 与完整五阶段 Fake E2E 全部通过。
