# Tool Security and Capability Requests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现由主进程重新鉴权的核心工具目录、Windows 路径防逃逸、CapabilityRequest、受控进程与完整审计。

**Architecture:** Worker 只能提交结构化 ToolExecutionRequest。Main Process 用角色、StageContract、Workspace、StageRun、槽位和工具策略求交集；ALLOW 才执行，REQUIRE 创建用户请求并暂停，DENY 永不启动工具。

**Tech Stack:** Python 3.12, Pydantic v2, pathlib, Windows reparse-point checks, psutil, asyncio subprocess, SQLAlchemy, pytest, hypothesis.

---

## File Map

```text
backend/src/agent_platform/
├─ domain/tools/{models.py,catalog.py,policy.py,capability.py}
├─ application/tools/{authorization_service.py,execution_service.py,capability_service.py}
├─ ports/{tool.py,process_runner.py}
├─ infrastructure/tools/{path_guard.py,filesystem.py,process_runner.py,git_tools.py,project_commands.py}
├─ infrastructure/database/tool_models.py
└─ interfaces/api/routes/capability_requests.py
```

### Task 1: Typed Tool Catalog and Permanent Slot Denials

**Files:**
- Create: `backend/src/agent_platform/domain/tools/models.py`
- Create: `backend/src/agent_platform/domain/tools/catalog.py`
- Test: `backend/tests/unit/test_tool_catalog.py`

- [ ] **Step 1: Write failing catalog tests**

```python
def test_catalog_contains_only_mvp_tools() -> None:
    names = ToolCatalog.default().names()
    assert "filesystem.read" in names
    assert "project.test" in names
    assert "git.push" not in names
    assert "network.request" not in names


@pytest.mark.parametrize("slot", [Slot.REVIEWER_A, Slot.REVIEWER_B])
def test_reviewers_receive_no_tool_schemas(slot: Slot) -> None:
    assert ToolCatalog.default().schemas_for(slot, Stage.BUILDER) == []
```

- [ ] **Step 2: Define request/result models**

```python
class PolicyDecision(StrEnum):
    ALLOW = "allow"
    REQUIRE_CAPABILITY_REQUEST = "require_capability_request"
    DENY = "deny"


class ToolExecutionRequest(BaseModel):
    request_id: str
    project_id: str
    workflow_id: str
    stage_run_id: str
    room_id: str
    task_id: str
    slot: Slot
    tool_name: str
    arguments: dict[str, JsonValue]


class ToolResult(BaseModel):
    request_id: str
    tool_name: str
    status: Literal["completed", "failed", "denied", "cancelled", "authorization_required"]
    data_ref: str | None = None
    stdout_ref: str | None = None
    stderr_ref: str | None = None
    exit_code: int | None = None
    affected_files: list[str] = Field(default_factory=list)
    duration_ms: int
    error: ErrorPayload | None = None
```

- [ ] **Step 3: Register exact MVP tools**

Register file read/search/list/write/create_directory/move/delete/hash/diff; Git status/diff/log/branch_info/hidden_checkpoint; shell.run_allowed; project build/test/lint/typecheck/security_scan. Each `ToolDefinition` declares JSON schema, risk level, read/write effect, default timeout, max output, and whether CapabilityRequest is possible. No arbitrary network/download, push, publish or remote deploy tool.

- [ ] **Step 4: Verify and commit**

```powershell
uv run pytest tests/unit/test_tool_catalog.py -v
git add backend/src/agent_platform/domain/tools backend/tests/unit/test_tool_catalog.py
git commit -m "feat: define controlled tool catalog"
```

### Task 2: Policy Intersection and Stage Boundaries

**Files:**
- Create: `backend/src/agent_platform/domain/tools/policy.py`
- Create: `backend/src/agent_platform/application/tools/authorization_service.py`
- Test: `backend/tests/unit/test_tool_policy.py`

- [ ] **Step 1: Write failing policy matrix tests**

```python
@pytest.mark.parametrize(("stage", "tool", "decision"), [
    (Stage.PLANNER, "filesystem.write", PolicyDecision.ALLOW),
    (Stage.PLANNER, "project.test", PolicyDecision.REQUIRE_CAPABILITY_REQUEST),
    (Stage.BUILDER, "project.test", PolicyDecision.ALLOW),
    (Stage.REVIEWER, "filesystem.write", PolicyDecision.DENY),
    (Stage.DEPLOYER, "project.build", PolicyDecision.DENY),
])
def test_role_contract_policy(stage, tool, decision) -> None:
    assert evaluate_policy(make_context(stage=stage, tool=tool)).decision is decision


def test_user_grant_cannot_override_permanent_denial() -> None:
    context = make_context(stage=Stage.REVIEWER, tool="filesystem.write", approved_grant=True)
    assert evaluate_policy(context).decision is PolicyDecision.DENY
```

- [ ] **Step 2: Implement pure policy intersection**

```python
@dataclass(frozen=True)
class PolicyContext:
    role_capabilities: frozenset[str]
    contract_default: frozenset[str]
    contract_requestable: frozenset[str]
    contract_denied: frozenset[str]
    workspace_capabilities: frozenset[str]
    stage_state: StageRunState
    slot: Slot
    requested_capability: str
    active_grants: tuple[CapabilityGrant, ...]
```

Reviewer slots always DENY. Completed consultation always DENY. Permanently denied wins before grants. Default intersection ALLOW; requestable and otherwise valid REQUIRE; everything else DENY. The application service reloads authoritative stage/profile/workspace state from repositories and ignores Worker-supplied role or grant claims.

- [ ] **Step 3: Run matrix tests and commit**

```powershell
uv run pytest tests/unit/test_tool_policy.py -v
git add backend/src/agent_platform/domain/tools/policy.py backend/src/agent_platform/application/tools/authorization_service.py backend/tests/unit/test_tool_policy.py
git commit -m "feat: enforce tool policy intersection"
```

### Task 3: Windows Path Guard and Reparse-Point Defense

**Files:**
- Create: `backend/src/agent_platform/infrastructure/tools/path_guard.py`
- Test: `backend/tests/security/test_path_guard.py`

- [ ] **Step 1: Write path escape tests**

```python
@pytest.mark.parametrize("candidate", [
    "../secret.txt", "C:/Windows/System32/config", "D:relative.txt",
    "//server/share/file", "\\\\server\\share\\file", "/absolute/file",
])
def test_rejects_non_project_paths(guard: PathGuard, candidate: str) -> None:
    with pytest.raises(PathDenied):
        guard.resolve_for_read(candidate)


def test_rejects_junction_that_points_outside_project(guard: PathGuard, escaped_junction: Path) -> None:
    with pytest.raises(PathDenied):
        guard.resolve_for_read("linked/secret.txt")
```

- [ ] **Step 2: Implement canonical comparison**

Reject NUL, device paths, drive-relative paths, absolute/UNC inputs and parent traversal before filesystem access. Resolve root and every existing ancestor; on Windows inspect `FILE_ATTRIBUTE_REPARSE_POINT` and final target. Compare with `os.path.normcase` plus `Path.relative_to`, never string prefix. Nonexistent write target is allowed only when its closest existing parent is safe. Then apply readable/writable patterns, protected patterns and `.agentignore`.

- [ ] **Step 3: Add property tests**

Use Hypothesis to generate mixed `/\\`, dot segments, case variants and Unicode names. Invariant: any returned path is absolute and `is_relative_to(canonical_root)` under case-insensitive comparison.

- [ ] **Step 4: Run Windows security tests and commit**

```powershell
uv run pytest tests/security/test_path_guard.py -v
git add backend/src/agent_platform/infrastructure/tools/path_guard.py backend/tests/security/test_path_guard.py
git commit -m "feat: prevent workspace path escape"
```

### Task 4: Atomic Filesystem Tools and Planned Writes

**Files:**
- Create: `backend/src/agent_platform/ports/tool.py`
- Create: `backend/src/agent_platform/infrastructure/tools/filesystem.py`
- Create: `backend/src/agent_platform/application/tools/execution_service.py`
- Test: `backend/tests/integration/test_filesystem_tools.py`

- [ ] **Step 1: Write failing atomic conflict test**

```python
@pytest.mark.asyncio
async def test_user_change_before_rename_creates_conflict_and_preserves_user_file(tool_service, project_file: Path) -> None:
    base = sha256_file(project_file)
    operation = await tool_service.prepare_write("task_1", "src/app.py", "agent content", base)
    project_file.write_text("user content", encoding="utf-8")

    result = await tool_service.commit_write(operation.id)

    assert result.status == "failed"
    assert result.error.code == "file.external_conflict"
    assert project_file.read_text(encoding="utf-8") == "user content"
```

- [ ] **Step 2: Implement read-only file tools**

Read/list/search/hash/diff always use PathGuard, byte/output limits and UTF-8 with explicit binary response references. Search accepts pattern and glob separately and does not invoke a shell. Results expose project-relative paths only.

- [ ] **Step 3: Implement mutation tools**

Write uses sibling temp file, flush, `os.fsync`, compares current Hash to planned base, registers planned write, then `os.replace`. Move/delete validate source and destination independently; recursive delete/move requires an approved capability or default Builder path policy and a protection checkpoint. No operation follows links or overwrites an externally changed target.

- [ ] **Step 4: Run integration tests and commit**

```powershell
uv run pytest tests/integration/test_filesystem_tools.py -v
git add backend/src/agent_platform/ports/tool.py backend/src/agent_platform/infrastructure/tools/filesystem.py backend/src/agent_platform/application/tools/execution_service.py backend/tests/integration/test_filesystem_tools.py
git commit -m "feat: execute atomic filesystem tools"
```

### Task 5: Short-Lived Shell, Git and Project Command Processes

**Files:**
- Create: `backend/src/agent_platform/ports/process_runner.py`
- Create: `backend/src/agent_platform/infrastructure/tools/process_runner.py`
- Create: `backend/src/agent_platform/infrastructure/tools/git_tools.py`
- Create: `backend/src/agent_platform/infrastructure/tools/project_commands.py`
- Test: `backend/tests/process/test_tool_process.py`
- Test: `backend/tests/security/test_shell_policy.py`

- [ ] **Step 1: Write timeout, injection and cleanup tests**

```python
@pytest.mark.asyncio
async def test_arguments_are_not_interpreted_as_powershell(runner: ProcessRunner, workspace: Path) -> None:
    result = await runner.run(ProcessSpec(
        executable=sys.executable,
        arguments=["-c", "import sys; print(sys.argv[1])", "; Remove-Item -Recurse C:\\"],
        cwd=workspace,
        timeout_seconds=5,
    ))
    assert result.stdout.strip() == "; Remove-Item -Recurse C:\\"


@pytest.mark.asyncio
async def test_timeout_kills_descendant_processes(runner: ProcessRunner, child_spawner: Path) -> None:
    result = await runner.run(ProcessSpec(sys.executable, [str(child_spawner)], child_spawner.parent, 0.2))
    assert result.timed_out is True
    assert no_descendant_processes(result.pid)
```

- [ ] **Step 2: Implement ProcessSpec and runner**

```python
class ProcessSpec(BaseModel):
    executable: str
    arguments: list[str]
    cwd: Path
    environment: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float = Field(gt=0, le=3600)
    max_output_bytes: int = Field(default=2_000_000, ge=1024)
    allowed_write_paths: list[str] = Field(default_factory=list)
    expected_effects: list[str] = Field(default_factory=list)
```

Use `create_subprocess_exec`, never `shell=True`. Build an allowlisted environment that removes credentials, provider keys, SSH, cloud and browser variables. Stream stdout/stderr separately with byte caps; overflow goes to a protected log reference. Cancellation/timeout terminates the full psutil process tree.

- [ ] **Step 3: Implement Git/project wrappers**

Git wrapper exposes only status/diff/log/branch_info/hidden_checkpoint with fixed argument builders. It has no push/publish/remote mutation. Project commands can run only exact `CommandSpec` entries from ProjectManifest. Deployer contract returns DENY for build/test/package even if a command exists.

- [ ] **Step 4: Run process/security tests and commit**

```powershell
uv run pytest tests/process/test_tool_process.py tests/security/test_shell_policy.py -v
git add backend/src/agent_platform/ports/process_runner.py backend/src/agent_platform/infrastructure/tools backend/tests/process/test_tool_process.py backend/tests/security/test_shell_policy.py
git commit -m "feat: run controlled tool processes"
```

### Task 6: CapabilityRequest Lifecycle in Both Approval Modes

**Files:**
- Create: `backend/src/agent_platform/domain/tools/capability.py`
- Create: `backend/src/agent_platform/application/tools/capability_service.py`
- Create: `backend/src/agent_platform/infrastructure/database/tool_models.py`
- Create: `backend/migrations/versions/0007_tools_capabilities.py`
- Test: `backend/tests/integration/test_capability_requests.py`

- [ ] **Step 1: Write failing mode-independent approval tests**

```python
@pytest.mark.parametrize("mode", [ApprovalMode.MANUAL, ApprovalMode.AUTONOMOUS])
@pytest.mark.asyncio
async def test_request_waits_for_user_in_every_mode(mode, service: CapabilityService) -> None:
    request = await service.request(make_tool_request(mode=mode))
    assert request.status is CapabilityStatus.PENDING
    assert request.requires_user_decision is True
```

- [ ] **Step 2: Implement request and grant types**

```python
class CapabilityStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    REVOKED = "revoked"


@dataclass(frozen=True)
class CapabilityGrant:
    request_id: str
    task_id: str
    capability: str
    target_paths: tuple[str, ...]
    command_fingerprint: str | None
    expires_at: datetime
```

Request records requester role, exact paths, command+arguments, expected changes, risk and reason. Approval binds to current task, fingerprint and expiry. Task completion/cancel, Worker restart or expiry revokes it. Permanent denies cannot create a request and return `tool.capability_not_requestable`.

- [ ] **Step 3: Persist and emit events**

Create `capability_requests` and `tool_calls` tables from `docs/09-data-model.md`. Request creation, `capability.requested`, and ToolCall pause are one transaction. Decision emits `capability.decided` and resumes only the original pending ToolCall after re-running full policy.

- [ ] **Step 4: Run tests and commit**

```powershell
uv run alembic upgrade head
uv run pytest tests/integration/test_capability_requests.py -v
git add backend/src/agent_platform/domain/tools/capability.py backend/src/agent_platform/application/tools/capability_service.py backend/src/agent_platform/infrastructure/database/tool_models.py backend/migrations/versions/0007_tools_capabilities.py backend/tests/integration/test_capability_requests.py
git commit -m "feat: require user capability decisions"
```

### Task 7: Tool Audit, Output References and Failure Semantics

**Files:**
- Modify: `backend/src/agent_platform/application/tools/execution_service.py`
- Create: `backend/src/agent_platform/infrastructure/tools/output_store.py`
- Test: `backend/tests/integration/test_tool_audit.py`

- [ ] **Step 1: Write failing audit tests**

Assert every allow/require/deny call records project, stage, Room, Task, Primary Profile, redacted and normalized arguments, policy decision, capability request, PID, times, exit code, output references, affected files and terminal status. Inject an audit repository failure and assert a high-risk process never starts.

- [ ] **Step 2: Implement redaction and output storage**

Redact values for keys matching token/secret/password/authorization/api_key and any environment value identified as sensitive. Large stdout/stderr is stored below application logs using random ids and SHA-256; ToolResult contains refs, bounded previews and hashes, not unbounded text.

- [ ] **Step 3: Implement truthful failure mapping**

DENY returns structured denial without execution. REQUIRE returns authorization_required. Nonzero exit returns failed with real code. Process crash/partial write marks Task non-complete and triggers workspace diff inspection. Audit commit is required before high-risk process spawn and final ToolCall status is committed before result ACK.

- [ ] **Step 4: Verify and commit**

```powershell
uv run pytest tests/integration/test_tool_audit.py -v
git add backend/src/agent_platform/application/tools/execution_service.py backend/src/agent_platform/infrastructure/tools/output_store.py backend/tests/integration/test_tool_audit.py
git commit -m "feat: audit tool execution results"
```

### Task 8: CapabilityRequest and Tool Audit APIs

**Files:**
- Create: `backend/src/agent_platform/interfaces/api/routes/capability_requests.py`
- Create: `backend/src/agent_platform/interfaces/api/routes/tool_calls.py`
- Test: `backend/tests/contract/test_tool_security_api.py`

- [ ] **Step 1: Test API contracts**

Cover request list/get/approve/reject and project tool-call cursor list. Approval/rejection requires Idempotency-Key. Verify both approval modes produce the same pending dialog data, API exposes only redacted arguments/output refs, and expired/task-mismatched decisions return stable conflicts.

- [ ] **Step 2: Implement routes and full verification**

```powershell
uv run pytest tests/contract/test_tool_security_api.py -v
uv run pytest tests/security tests/process tests/integration/test_filesystem_tools.py tests/integration/test_capability_requests.py -v
uv run ruff format --check .
uv run ruff check .
uv run mypy src
```

- [ ] **Step 3: Commit**

```powershell
git add backend/src/agent_platform/interfaces/api/routes/capability_requests.py backend/src/agent_platform/interfaces/api/routes/tool_calls.py backend/tests/contract/test_tool_security_api.py
git commit -m "feat: expose capability and tool audit api"
```

## Definition of Done

- Reviewer 槽位的任何 ToolExecutionRequest 都在执行前 DENY。
- Prompt、Worker、Shell 和已批准 CapabilityRequest 都不能突破永久禁止或项目根边界。
- MANUAL/AUTONOMOUS 的合法越权申请均等待用户弹窗，任务或 Worker 结束即失效。
- Shell 使用 executable+arguments、脱敏环境、超时、输出上限和完整进程树清理。
- 同文件并发修改不覆盖用户内容，所有工具结果可审计且不泄漏密钥。
