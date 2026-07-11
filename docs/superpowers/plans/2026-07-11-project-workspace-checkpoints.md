# Projects, Workspaces and Checkpoints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现项目登记、Managed/Direct Workspace、项目预检、ProjectManifest、内容寻址检查点、外部修改检测与三方文件冲突。

**Architecture:** Backend Main Process 独占工作区状态和快照元数据。项目文件保留在工作区，快照对象存入应用数据目录；所有路径先规范化，所有恢复和并发写入通过版本 Hash 防止静默覆盖。

**Tech Stack:** Python 3.12, Pydantic v2, SQLAlchemy Async, SQLite, Alembic, watchfiles, zstandard, hashlib, pytest, hypothesis.

---

## File Map

```text
backend/src/agent_platform/
├─ domain/projects/
│  ├─ models.py
│  ├─ manifest.py
│  ├─ preflight.py
│  └─ conflicts.py
├─ application/projects/
│  ├─ service.py
│  ├─ preflight_service.py
│  ├─ checkpoint_service.py
│  └─ external_change_service.py
├─ ports/
│  ├─ project_repository.py
│  ├─ workspace.py
│  └─ snapshot_store.py
├─ infrastructure/
│  ├─ database/project_models.py
│  ├─ database/project_repositories.py
│  ├─ workspaces/local_workspace.py
│  ├─ snapshots/content_store.py
│  └─ watching/project_watcher.py
└─ interfaces/api/routes/projects.py
```

### Task 1: Project and Workspace Persistence

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock`
- Create: `backend/src/agent_platform/domain/projects/models.py`
- Create: `backend/src/agent_platform/infrastructure/database/project_models.py`
- Create: `backend/src/agent_platform/infrastructure/database/project_repositories.py`
- Create: `backend/migrations/versions/0002_projects_workspaces.py`
- Test: `backend/tests/integration/test_project_repository.py`

- [ ] **Step 1: Write the failing repository test**

```python
@pytest.mark.asyncio
async def test_project_and_workspace_round_trip(database: Database, tmp_path: Path) -> None:
    repository = SqlProjectRepository(database.sessions)
    project = Project(
        id="project_1",
        name="Demo",
        description="",
        state=ProjectState.READY,
        workspace=Workspace(
            id="workspace_1",
            project_id="project_1",
            mode=WorkspaceMode.DIRECT,
            root_path=tmp_path,
        ),
    )

    await repository.add(project)
    loaded = await repository.get("project_1")

    assert loaded == project
```

Before running the test, add runtime dependencies `pathspec>=0.12,<1`, `watchfiles>=1.0,<2`, and `zstandard>=0.23,<1`, plus dev dependency `hypothesis>=6.120,<7`, then run `uv lock`.

- [ ] **Step 2: Run it and confirm the missing implementation**

```powershell
uv run pytest tests/integration/test_project_repository.py -v
```

Expected: FAIL with missing `domain.projects.models`.

- [ ] **Step 3: Implement domain records**

```python
class WorkspaceMode(StrEnum):
    MANAGED = "managed"
    DIRECT = "direct"


class ProjectState(StrEnum):
    READY = "ready"
    PREFLIGHT_FAILED = "preflight_failed"
    EXTERNAL_CONFLICT = "external_conflict"
    REMOVED = "removed"


@dataclass(frozen=True)
class Workspace:
    id: str
    project_id: str
    mode: WorkspaceMode
    root_path: Path
    manifest_version: int = 0
    current_checkpoint_id: str | None = None
    watch_state: str = "stopped"


@dataclass(frozen=True)
class Project:
    id: str
    name: str
    description: str
    state: ProjectState
    workspace: Workspace
    current_workflow_id: str | None = None
    version: int = 1
```

- [ ] **Step 4: Add ORM rows, migration and repository mapping**

Create `projects` and `workspaces` with explicit foreign keys, unique `workspace.project_id`, optimistic `version`, timestamps, and indexes on project state. Repository methods are `add`, `get`, `list`, `update(expected_version)`, and `remove_record`; they return domain records, never ORM rows. Version mismatch raises `DomainError(code="resource.version_conflict", ...)`.

- [ ] **Step 5: Verify migration and repository**

```powershell
uv run alembic upgrade head
uv run pytest tests/integration/test_project_repository.py -v
```

Expected: PASS and migration head is `0002_projects_workspaces`.

- [ ] **Step 6: Commit**

```powershell
git add backend/pyproject.toml backend/uv.lock backend/src/agent_platform/domain/projects backend/src/agent_platform/infrastructure/database backend/migrations/versions/0002_projects_workspaces.py backend/tests/integration/test_project_repository.py
git commit -m "feat: persist projects and workspaces"
```

### Task 2: ProjectManifest and `.agent` Metadata

**Files:**
- Create: `backend/src/agent_platform/domain/projects/manifest.py`
- Create: `backend/src/agent_platform/infrastructure/workspaces/local_workspace.py`
- Test: `backend/tests/unit/test_project_manifest.py`
- Test: `backend/tests/integration/test_agent_metadata.py`

- [ ] **Step 1: Write failing manifest tests**

```python
def test_manifest_rejects_absolute_and_parent_paths() -> None:
    with pytest.raises(ValidationError):
        ProjectManifest(schema_version=1, project_type="web", source_roots=["../src"])
    with pytest.raises(ValidationError):
        ProjectManifest(schema_version=1, project_type="web", source_roots=["C:/src"])


def test_manifest_normalizes_commands_without_shell_string() -> None:
    manifest = ProjectManifest(
        schema_version=1,
        project_type="web",
        build_commands=[CommandSpec(executable="npm", arguments=["run", "build"], cwd=".")],
    )
    assert manifest.build_commands[0].arguments == ["run", "build"]
```

- [ ] **Step 2: Run tests to verify failure**

```powershell
uv run pytest tests/unit/test_project_manifest.py -v
```

- [ ] **Step 3: Implement the schema**

```python
class CommandSpec(BaseModel):
    executable: str = Field(min_length=1)
    arguments: list[str] = Field(default_factory=list)
    cwd: str = "."
    timeout_seconds: int = Field(default=600, ge=1, le=3600)


class ProjectManifest(BaseModel):
    schema_version: Literal[1]
    project_type: str
    components: list[str] = Field(default_factory=list)
    entrypoints: list[str] = Field(default_factory=list)
    source_roots: list[str] = Field(default_factory=list)
    test_roots: list[str] = Field(default_factory=list)
    dependency_files: list[str] = Field(default_factory=list)
    build_commands: list[CommandSpec] = Field(default_factory=list)
    test_commands: list[CommandSpec] = Field(default_factory=list)
    lint_commands: list[CommandSpec] = Field(default_factory=list)
    typecheck_commands: list[CommandSpec] = Field(default_factory=list)
    runtime_commands: list[CommandSpec] = Field(default_factory=list)
    environment_files: list[str] = Field(default_factory=list)
    generated_paths: list[str] = Field(default_factory=list)
    protected_paths: list[str] = Field(default_factory=list)
```

Every path field uses one validator that converts `\\` to `/`, rejects absolute, drive-qualified, UNC and `..`, and removes duplicate normalized paths.

- [ ] **Step 4: Implement atomic metadata I/O**

`LocalWorkspace.ensure_metadata()` creates `.agent/`, `.agent/project.json`, `.agent/project-manifest.json`, `.agent/contracts.json`, and `.agent/.agentignore` using temp-file + `os.replace`. Existing files are parsed before replacement; invalid existing JSON raises `project.metadata_invalid` and is never overwritten.

- [ ] **Step 5: Run tests**

```powershell
uv run pytest tests/unit/test_project_manifest.py tests/integration/test_agent_metadata.py -v
```

- [ ] **Step 6: Commit**

```powershell
git add backend/src/agent_platform/domain/projects/manifest.py backend/src/agent_platform/infrastructure/workspaces backend/tests/unit/test_project_manifest.py backend/tests/integration/test_agent_metadata.py
git commit -m "feat: define project manifest metadata"
```

### Task 3: Managed and Direct Workspace Creation

**Files:**
- Create: `backend/src/agent_platform/ports/workspace.py`
- Create: `backend/src/agent_platform/application/projects/service.py`
- Modify: `backend/src/agent_platform/config/settings.py`
- Test: `backend/tests/integration/test_workspace_service.py`

- [ ] **Step 1: Write failing workspace mode tests**

```python
@pytest.mark.asyncio
async def test_direct_workspace_keeps_user_root(tmp_path: Path, service: ProjectService) -> None:
    project = await service.create_project("Demo", WorkspaceMode.DIRECT, tmp_path)
    assert project.workspace.root_path == tmp_path.resolve()


@pytest.mark.asyncio
async def test_managed_workspace_copies_source_without_git_mutation(
    tmp_path: Path, settings: Settings, service: ProjectService
) -> None:
    source = tmp_path / "source"
    (source / "src").mkdir(parents=True)
    (source / "src/app.py").write_text("print('ok')", encoding="utf-8")

    project = await service.create_project("Demo", WorkspaceMode.MANAGED, source)

    assert project.workspace.root_path.parent == settings.managed_workspace_root
    assert (project.workspace.root_path / "src/app.py").read_text(encoding="utf-8") == "print('ok')"
    assert not (source / ".agent").exists()
```

- [ ] **Step 2: Run tests to verify failure**

```powershell
uv run pytest tests/integration/test_workspace_service.py -v
```

- [ ] **Step 3: Define the workspace port and service**

```python
class WorkspacePort(Protocol):
    async def prepare_direct(self, root: Path) -> Path: ...
    async def prepare_managed(self, source: Path, destination: Path) -> Path: ...
    async def read_manifest(self, root: Path) -> ProjectManifest: ...
    async def write_manifest(self, root: Path, manifest: ProjectManifest) -> None: ...


class ProjectService:
    async def create_project(
        self, name: str, mode: WorkspaceMode, selected_root: Path
    ) -> Project: ...
```

Add `managed_workspace_root = data_root / "managed-workspaces"`. Reject missing roots, file roots, application data roots, Windows system directories, and roots containing an unresolved reparse-point escape. Managed copy obeys default ignores and never executes Git commands.

- [ ] **Step 4: Run tests and path cases**

```powershell
uv run pytest tests/integration/test_workspace_service.py -v
uv run pytest tests/security -k workspace -v
```

- [ ] **Step 5: Commit**

```powershell
git add backend/src/agent_platform/ports/workspace.py backend/src/agent_platform/application/projects/service.py backend/src/agent_platform/config/settings.py backend/tests/integration/test_workspace_service.py backend/tests/security/test_workspace_roots.py
git commit -m "feat: create managed and direct workspaces"
```

### Task 4: Deterministic Project Preflight Gate

**Files:**
- Create: `backend/src/agent_platform/domain/projects/preflight.py`
- Create: `backend/src/agent_platform/application/projects/preflight_service.py`
- Test: `backend/tests/unit/test_preflight_rules.py`
- Test: `backend/tests/integration/test_project_preflight.py`

- [ ] **Step 1: Write failing rule tests**

```python
def test_existing_failed_test_blocks_workflow() -> None:
    report = evaluate_preflight([
        PreflightCheck(name="build", status=CheckStatus.PASS),
        PreflightCheck(name="test", status=CheckStatus.FAIL, evidence_ref="log://test"),
    ])
    assert report.status is PreflightStatus.FAILED
    assert report.can_start_workflow is False


def test_missing_test_command_is_allowed_and_recorded() -> None:
    report = evaluate_preflight([
        PreflightCheck(name="build", status=CheckStatus.PASS),
        PreflightCheck(name="test", status=CheckStatus.NOT_CONFIGURED),
    ])
    assert report.status is PreflightStatus.PASS_WITH_REQUIREMENT
    assert report.builder_must_create_tests is True
```

- [ ] **Step 2: Implement preflight value objects and evaluator**

```python
class CheckStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NOT_CONFIGURED = "not_configured"


class PreflightStatus(StrEnum):
    PASSED = "passed"
    PASS_WITH_REQUIREMENT = "pass_with_requirement"
    FAILED = "failed"


@dataclass(frozen=True)
class PreflightReport:
    status: PreflightStatus
    checks: tuple[PreflightCheck, ...]
    can_start_workflow: bool
    builder_must_create_tests: bool
```

- [ ] **Step 3: Implement the service**

The service validates metadata, manifest paths, entrypoints, dependencies, unresolved conflicts, and symlink/junction boundaries. It runs only manifest-declared build/test/lint/typecheck commands through a temporary `PreflightCommandPort`; every result records exit code, duration and log reference. Any declared command failure rejects startup. It reports evidence but never invokes an Agent to fix the project.

- [ ] **Step 4: Verify all four project cases**

```powershell
uv run pytest tests/unit/test_preflight_rules.py tests/integration/test_project_preflight.py -v
```

Expected: new project passes, healthy existing project passes, no-test project passes with Builder requirement, failed existing build/test is rejected.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/agent_platform/domain/projects/preflight.py backend/src/agent_platform/application/projects/preflight_service.py backend/tests/unit/test_preflight_rules.py backend/tests/integration/test_project_preflight.py
git commit -m "feat: enforce project preflight gate"
```

### Task 5: Content-Addressed Incremental Snapshot Store

**Files:**
- Create: `backend/src/agent_platform/ports/snapshot_store.py`
- Create: `backend/src/agent_platform/infrastructure/snapshots/content_store.py`
- Create: `backend/src/agent_platform/domain/projects/checkpoints.py`
- Create: `backend/src/agent_platform/infrastructure/database/checkpoint_models.py`
- Create: `backend/migrations/versions/0003_checkpoints.py`
- Test: `backend/tests/integration/test_snapshot_store.py`

- [ ] **Step 1: Write failing deduplication test**

```python
@pytest.mark.asyncio
async def test_identical_files_share_one_snapshot_object(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "a.txt").write_text("same", encoding="utf-8")
    (workspace / "b.txt").write_text("same", encoding="utf-8")
    store = ContentAddressedSnapshotStore(tmp_path / "snapshots")

    checkpoint = await store.create_checkpoint("project_1", workspace, IgnoreRules.default())

    assert checkpoint.file_count == 2
    assert checkpoint.files[0].content_hash == checkpoint.files[1].content_hash
    assert len(list((tmp_path / "snapshots/objects").rglob("*.zst"))) == 1
```

- [ ] **Step 2: Implement checkpoint contracts**

```python
@dataclass(frozen=True)
class CheckpointFile:
    relative_path: str
    content_hash: str
    object_uri: str
    size: int
    file_mode: int
    modified_at_ns: int


@dataclass(frozen=True)
class ProjectCheckpoint:
    checkpoint_id: str
    project_id: str
    workflow_id: str | None
    stage_run_id: str | None
    workspace_mode: WorkspaceMode
    root_hash: str
    git_head: str | None
    manifest_uri: str
    files: tuple[CheckpointFile, ...]
```

- [ ] **Step 3: Implement object and manifest writes**

For each non-ignored regular file, stream SHA-256, store compressed bytes under `objects/<first-two>/<hash>.zst`, and never rewrite an existing object. Sort manifest entries by normalized relative path. Calculate `root_hash = sha256(canonical_json(entries))`. Write objects and manifests through temp files, `fsync`, and `os.replace`; remove incomplete temp files at next startup. Do not follow links and fail on a reparse point.

- [ ] **Step 4: Persist checkpoint metadata**

Add `project_checkpoints` and `checkpoint_files` exactly as specified in `docs/09-data-model.md`; SQLite stores only URIs and hashes. Repository insertion is one transaction and artifact/workflow plans will reference `checkpoint_id`.

- [ ] **Step 5: Run snapshot and migration tests**

```powershell
uv run alembic upgrade head
uv run pytest tests/integration/test_snapshot_store.py tests/migration -v
```

- [ ] **Step 6: Commit**

```powershell
git add backend/src/agent_platform/ports/snapshot_store.py backend/src/agent_platform/domain/projects/checkpoints.py backend/src/agent_platform/infrastructure/snapshots backend/src/agent_platform/infrastructure/database/checkpoint_models.py backend/migrations/versions/0003_checkpoints.py backend/tests/integration/test_snapshot_store.py
git commit -m "feat: create incremental project checkpoints"
```

### Task 6: Safe Checkpoint Restore

**Files:**
- Create: `backend/src/agent_platform/application/projects/checkpoint_service.py`
- Test: `backend/tests/integration/test_checkpoint_restore.py`

- [ ] **Step 1: Write failing restore tests**

```python
@pytest.mark.asyncio
async def test_restore_creates_protection_checkpoint_and_keeps_git_head(
    checkpoint_service: CheckpointService, workspace: Path
) -> None:
    original_head = read_git_head(workspace)
    target = await checkpoint_service.create("project_1", reason="target")
    (workspace / "app.txt").write_text("changed", encoding="utf-8")

    result = await checkpoint_service.restore("project_1", target.checkpoint_id)

    assert result.protection_checkpoint_id is not None
    assert (workspace / "app.txt").read_text(encoding="utf-8") == "original"
    assert read_git_head(workspace) == original_head
```

- [ ] **Step 2: Implement restore transaction boundaries**

`restore()` rejects unresolved `FileConflict`, creates a protection checkpoint, materializes every target file to a staging directory, verifies content and root hashes, then atomically replaces allowed files. It removes files absent from the target only after protection snapshot succeeds. It never runs `git checkout`, `git reset`, branch switch, commit, or clean. After success it records a new current checkpoint and returns the earliest invalidated stage.

- [ ] **Step 3: Run restore tests**

```powershell
uv run pytest tests/integration/test_checkpoint_restore.py -v
```

- [ ] **Step 4: Commit**

```powershell
git add backend/src/agent_platform/application/projects/checkpoint_service.py backend/tests/integration/test_checkpoint_restore.py
git commit -m "feat: restore project checkpoints safely"
```

### Task 7: External Changes and Three-Way File Conflicts

**Files:**
- Create: `backend/src/agent_platform/domain/projects/conflicts.py`
- Create: `backend/src/agent_platform/application/projects/external_change_service.py`
- Create: `backend/src/agent_platform/infrastructure/watching/project_watcher.py`
- Create: `backend/src/agent_platform/infrastructure/database/change_models.py`
- Create: `backend/migrations/versions/0004_external_changes.py`
- Test: `backend/tests/integration/test_external_changes.py`

- [ ] **Step 1: Write failing ownership and conflict tests**

```python
@pytest.mark.parametrize(("path", "stage"), [
    ("specs/requirements.md", Stage.PLANNER),
    ("specs/api.md", Stage.DESIGNER),
    ("src/app.py", Stage.BUILDER),
    ("specs/review.md", Stage.REVIEWER),
    ("specs/deployment/runbook.md", Stage.DEPLOYER),
])
def test_external_path_maps_to_earliest_owner(path: str, stage: Stage) -> None:
    assert owner_stage_for_path(path) is stage


@pytest.mark.asyncio
async def test_concurrent_user_and_agent_write_creates_three_way_conflict(service: ExternalChangeService) -> None:
    planned = await service.register_planned_write("task_1", "src/app.py", base_hash="base")
    conflict = await service.finish_agent_write(planned.id, agent_ref="obj://agent", observed_user_hash="user")
    assert conflict.base_ref == "obj://base"
    assert conflict.agent_ref == "obj://agent"
    assert conflict.user_ref == "obj://user"
    assert conflict.resolution is None
```

- [ ] **Step 2: Implement watcher and records**

`ProjectWatcher` wraps `watchfiles.awatch`, batches paths for 200 ms, ignores default and `.agentignore` patterns, hashes actual files, and forwards changes to the application service. Planned writes are matched by normalized path plus base hash. Unmatched changes create immutable `ExternalChangeRecord`; conflicting same-file writes create `FileConflict` and put project/workflow into `external_conflict`.

- [ ] **Step 3: Implement explicit resolutions**

```python
class ConflictResolution(StrEnum):
    KEEP_USER = "keep_user"
    KEEP_AGENT = "keep_agent"
    MANUAL_MERGE = "manual_merge"
```

`keep_user` keeps current workspace bytes; `keep_agent` materializes `agent_ref` only after current user hash still matches; `manual_merge` requires `resolved_ref` whose content hash matches the current file. Every resolution creates a protection checkpoint and triggers re-Gate. There is no automatic merge path.

- [ ] **Step 4: Run watcher/conflict tests**

```powershell
uv run alembic upgrade head
uv run pytest tests/integration/test_external_changes.py -v
```

- [ ] **Step 5: Commit**

```powershell
git add backend/src/agent_platform/domain/projects/conflicts.py backend/src/agent_platform/application/projects/external_change_service.py backend/src/agent_platform/infrastructure/watching backend/src/agent_platform/infrastructure/database/change_models.py backend/migrations/versions/0004_external_changes.py backend/tests/integration/test_external_changes.py
git commit -m "feat: track external file conflicts"
```

### Task 8: Project, Preflight, Manifest and Checkpoint APIs

**Files:**
- Create: `backend/src/agent_platform/interfaces/api/routes/projects.py`
- Create: `backend/src/agent_platform/interfaces/api/schemas/projects.py`
- Modify: `backend/src/agent_platform/bootstrap/app_factory.py`
- Test: `backend/tests/contract/test_projects_api.py`

- [ ] **Step 1: Write failing API contract tests**

Test authenticated create/list/get/patch/remove-record, preflight, manifest GET/PUT, workspace status, checkpoint list/get/restore, external changes and conflict resolution. Verify Direct Workspace deletion never removes project files and every mutation requires `Idempotency-Key` plus expected `version` where applicable.

- [ ] **Step 2: Implement routes through application services**

Implement the exact endpoints in sections 6, 14 and 15 of `docs/10-api-and-events.md`. Responses use `{"data": ..., "meta": {"request_id": ...}}`; no route imports ORM models or writes sessions directly. Paths returned to Renderer are project-relative except the user-selected workspace root in project details.

- [ ] **Step 3: Verify API and OpenAPI**

```powershell
uv run pytest tests/contract/test_projects_api.py -v
uv run python -c "from agent_platform.bootstrap.app_factory import dev_app; s=dev_app().openapi(); assert '/api/v1/projects/{project_id}/preflight' in s['paths']"
```

- [ ] **Step 4: Run plan-wide quality gates**

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest tests/unit tests/integration tests/contract tests/security tests/migration -v
```

- [ ] **Step 5: Commit**

```powershell
git add backend/src/agent_platform/interfaces/api backend/src/agent_platform/bootstrap/app_factory.py backend/tests/contract/test_projects_api.py
git commit -m "feat: expose project workspace api"
```

## Definition of Done

- 健康已有项目可进入；已有强制构建或测试失败的项目被拒绝；无测试项目带 Builder 强制要求进入。
- Managed 与 Direct Workspace 都不会修改用户 Git 分支。
- 相同文件内容在快照中只存一个对象，Manifest 与 root hash 可验证。
- 恢复前必有保护检查点，恢复不越过项目根目录。
- 外部变化映射到最早责任阶段，同文件并发写必然生成三方 `FileConflict`。
