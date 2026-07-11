# Stage Contracts, Gates and Handoffs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将五个角色职责实现为版本固定的 StageContract、确定性 Quality Gate、不可变交接包和结构化 ChangeRequest。

**Architecture:** 模型只提交草案和结构化声明；主进程读取真实文件、工具证据和检查点执行 Gate。正式阶段完成在一个 UnitOfWork 内锁定 Artifact、Checkpoint、Gate、Approval/Handoff、状态与事件。

**Tech Stack:** Python 3.12, Pydantic v2, SQLAlchemy Async, SHA-256 canonical JSON, pytest.

---

## File Map

```text
backend/src/agent_platform/
├─ domain/contracts/{models.py,loader.py,permission_calculator.py}
├─ domain/artifacts/{models.py,service.py}
├─ domain/gates/{models.py,planner.py,designer.py,builder.py,reviewer.py,deployer.py}
├─ domain/handoffs/{models.py,validation.py,change_requests.py}
├─ application/stages/{completion_service.py,warning_service.py,approval_service.py}
├─ application/handoffs/{service.py,change_request_service.py}
└─ interfaces/api/routes/{gates.py,approvals.py,handoffs.py,change_requests.py,artifacts.py}
```

### Task 1: Versioned StageContract Schemas and Five Contract Resources

**Files:**
- Create: `backend/src/agent_platform/domain/contracts/models.py`
- Create: `backend/src/agent_platform/domain/contracts/loader.py`
- Create: `backend/src/agent_platform/domain/contracts/permission_calculator.py`
- Create: `backend/src/agent_platform/resources/contracts/v1/*.json`
- Test: `backend/tests/contract/test_stage_contracts.py`

- [ ] **Step 1: Write failing contract tests**

```python
@pytest.mark.parametrize("stage", list(Stage))
def test_every_stage_contract_loads_and_has_pinned_versions(loader: ContractLoader, stage: Stage) -> None:
    contract = loader.load(stage, "1.0.0")
    assert contract.stage is stage
    assert contract.version == "1.0.0"
    assert contract.role_card_version == "1.0.0"
    assert contract.completion_requirements


def test_reviewer_write_is_permanently_denied(loader: ContractLoader) -> None:
    contract = loader.load(Stage.REVIEWER, "1.0.0")
    assert "source.write" in contract.permanently_denied_capabilities
```

- [ ] **Step 2: Implement the common schema**

```python
class StageContract(BaseModel):
    contract_id: str
    stage: Stage
    version: str
    role_card_version: str
    predecessor: Stage | None
    successor: Stage | None
    required_handoff_type: str | None
    allowed_inputs: list[str]
    required_outputs: list[str]
    readable_paths: list[str]
    writable_paths: list[str]
    immutable_paths: list[str]
    default_capabilities: list[str]
    requestable_capabilities: list[str]
    permanently_denied_capabilities: list[str]
    p2r_policy: P2RPolicy
    quality_checks: list[QualityCheckSpec]
    external_change_ownership: list[PathOwnershipRule]
    completion_requirements: list[str]
```

- [ ] **Step 3: Encode the five approved contracts**

Planner writes requirements only; Designer writes design/API/data/tasks and cannot alter requirements; Builder writes project code/tests/config/migrations but not upstream specs; Reviewer writes review evidence only and source/test changes are permanently denied; Deployer writes deployment docs/allowed deployment files, cannot modify business code and cannot run build/package/deploy. Loader validates stage order, no overlap between default/requestable/permanent deny, role card hash, and writable paths not intersecting immutable paths.

- [ ] **Step 4: Implement effective capability calculation**

Return the intersection used by Tool Policy plus normalized read/write patterns. A CapabilityRequest can add only an item in `requestable_capabilities`; permanent denial always wins.

- [ ] **Step 5: Verify and commit**

```powershell
uv run pytest tests/contract/test_stage_contracts.py -v
git add backend/src/agent_platform/domain/contracts backend/src/agent_platform/resources/contracts backend/tests/contract/test_stage_contracts.py
git commit -m "feat: define executable stage contracts"
```

### Task 2: Immutable Artifacts and StageDeliverables

**Files:**
- Create: `backend/src/agent_platform/domain/artifacts/models.py`
- Create: `backend/src/agent_platform/domain/artifacts/service.py`
- Create: `backend/src/agent_platform/infrastructure/database/artifact_models.py`
- Create: `backend/migrations/versions/0008_artifacts_gates.py`
- Test: `backend/tests/integration/test_artifact_versions.py`

- [ ] **Step 1: Write failing immutability tests**

```python
@pytest.mark.asyncio
async def test_formal_artifact_version_cannot_be_overwritten(service: ArtifactService) -> None:
    first = await service.create_version("artifact_1", "specs/requirements.md", b"v1", "run_1")
    second = await service.create_version("artifact_1", "specs/requirements.md", b"v2", "run_2")
    assert first.version == 1
    assert second.version == 2
    assert await service.read_version(first.id) == b"v1"
```

- [ ] **Step 2: Define formal records**

```python
class ArtifactVersionStatus(StrEnum):
    DRAFT = "draft"
    LOCKED = "locked"
    INVALIDATED = "invalidated"
    SUPERSEDED = "superseded"


class StageDeliverable(BaseModel):
    deliverable_id: str
    stage_run_id: str
    stage: Stage
    project_checkpoint_ref: ProjectCheckpointRef
    artifact_version_ids: list[str]
    result_summary: str
    evidence_refs: list[str]
    created_at: datetime
```

Artifact metadata is backend-generated from actual bytes and project-relative paths. A model cannot provide `approved`, Hash or version. Formal deliverable always references a completed immutable checkpoint.

- [ ] **Step 3: Add tables and repositories**

Create `artifacts`, `artifact_versions`, `quality_gate_runs`, `quality_gate_issues` and indexes from `docs/09-data-model.md`. Artifact content remains in workspace/checkpoint store; SQLite contains version metadata and hashes.

- [ ] **Step 4: Verify and commit**

```powershell
uv run alembic upgrade head
uv run pytest tests/integration/test_artifact_versions.py -v
git add backend/src/agent_platform/domain/artifacts backend/src/agent_platform/infrastructure/database/artifact_models.py backend/migrations/versions/0008_artifacts_gates.py backend/tests/integration/test_artifact_versions.py
git commit -m "feat: version formal stage artifacts"
```

### Task 3: Common Gate Engine and Result Semantics

**Files:**
- Create: `backend/src/agent_platform/domain/gates/models.py`
- Create: `backend/src/agent_platform/domain/gates/engine.py`
- Test: `backend/tests/unit/test_gate_engine.py`

- [ ] **Step 1: Write failing result merge tests**

```python
@pytest.mark.parametrize(("issues", "expected"), [
    ([], GateStatus.PASS),
    ([issue(Severity.WARNING, blocking=False)], GateStatus.WARNING),
    ([issue(Severity.ERROR, code="fixable", blocking=True)], GateStatus.NEEDS_FIX),
    ([issue(Severity.FATAL, code="unsafe", blocking=True)], GateStatus.FAIL),
])
def test_gate_status_is_deterministic(issues, expected) -> None:
    assert calculate_gate_status(issues) is expected
```

- [ ] **Step 2: Implement evidence-first gate types**

```python
class GateStatus(StrEnum):
    PASS = "pass"
    WARNING = "warning"
    NEEDS_FIX = "needs_fix"
    FAIL = "fail"


class GateIssue(BaseModel):
    severity: Severity
    code: str
    message: str
    evidence_ref: str | None
    affected_file: str | None
    is_blocking: bool
    target_stage: Stage | None
```

GateRunner receives Contract, StageDeliverable, ProjectCheckpoint, P2R results and real ToolCall evidence. Checks return issues, never directly change state. Fatal integrity/safety/false-evidence failures map FAIL; repairable contract gaps map NEEDS_FIX; explicit non-blocking uncertainty maps WARNING.

- [ ] **Step 3: Enforce P2R completion**

Formal gate refuses missing Reviewer A/B assignments, missing ReviewResult, unresolved BLOCK, or a model-produced claim without corresponding Artifact/Tool evidence.

- [ ] **Step 4: Verify and commit**

```powershell
uv run pytest tests/unit/test_gate_engine.py -v
git add backend/src/agent_platform/domain/gates backend/tests/unit/test_gate_engine.py
git commit -m "feat: evaluate deterministic quality gates"
```

### Task 4: Planner and Designer Gates

**Files:**
- Create: `backend/src/agent_platform/domain/gates/planner.py`
- Create: `backend/src/agent_platform/domain/gates/designer.py`
- Test: `backend/tests/contract/test_planner_designer_gates.py`

- [ ] **Step 1: Write failing legal/illegal cases**

Planner tests duplicate requirement ids, missing acceptance criteria, missing scope/non-goals/risks/decisions and blocking open questions. Designer tests every core requirement maps to design, API/data/state/error/security definitions exist, Builder tasks contain goal/dependencies/file scope/tests, and changed requirement text without Planner ChangeRequest is rejected.

- [ ] **Step 2: Implement parsers and checks**

Use deterministic Markdown front-matter and heading parsers. Requirements use `REQ-<number>` and `AC-<number>` references. Design mapping table contains `requirement_id`, `components`, `interfaces`, `data`, and `builder_tasks`. Do not ask a model to decide whether sections exist.

- [ ] **Step 3: Verify**

```powershell
uv run pytest tests/contract/test_planner_designer_gates.py -v
```

- [ ] **Step 4: Commit**

```powershell
git add backend/src/agent_platform/domain/gates/planner.py backend/src/agent_platform/domain/gates/designer.py backend/tests/contract/test_planner_designer_gates.py
git commit -m "feat: validate planning and design outputs"
```

### Task 5: Builder, Reviewer and Deployer Gates

**Files:**
- Create: `backend/src/agent_platform/domain/gates/builder.py`
- Create: `backend/src/agent_platform/domain/gates/reviewer.py`
- Create: `backend/src/agent_platform/domain/gates/deployer.py`
- Test: `backend/tests/contract/test_delivery_gates.py`

- [ ] **Step 1: Write failing Builder cases**

Assert ProjectManifest references real files/commands; every declared build/test/lint/typecheck result is successful and from current checkpoint; missing tests are allowed only when preflight created a mandatory testing task and Builder now adds tests; critical placeholders (`pass`, `NotImplementedError`, empty handler, fake success report) block handoff; upstream contract deviation creates NEEDS_FIX/ChangeRequest.

- [ ] **Step 2: Write Reviewer cases**

PASS cannot coexist with blocking findings. Every core requirement needs implementation and independent command evidence. Blocking finding includes severity, evidence and target stage. Reviewer source/test write attempts are FAIL-level policy evidence. Only PASS may proceed to Deployer.

- [ ] **Step 3: Write Deployer cases**

Require deployment plan, environment, start/stop, health, logs, backup and rollback sections; every generated deployment file is referenced; secret scanner finds no real credential; unverified assumptions are labeled. Any ToolCall for Docker build, package validation, remote connection, push, publish or deployment is a blocking failure. Business source changes are rejected.

- [ ] **Step 4: Implement and verify**

```powershell
uv run pytest tests/contract/test_delivery_gates.py -v
git add backend/src/agent_platform/domain/gates/builder.py backend/src/agent_platform/domain/gates/reviewer.py backend/src/agent_platform/domain/gates/deployer.py backend/tests/contract/test_delivery_gates.py
git commit -m "feat: validate build review and deployment outputs"
```

### Task 6: MANUAL Approval and AUTONOMOUS Warning Blocking

**Files:**
- Create: `backend/src/agent_platform/application/stages/approval_service.py`
- Create: `backend/src/agent_platform/application/stages/warning_service.py`
- Create: `backend/src/agent_platform/infrastructure/database/approval_models.py`
- Create: `backend/migrations/versions/0009_approvals_handoffs.py`
- Test: `backend/tests/integration/test_gate_decisions.py`

- [ ] **Step 1: Write the decision matrix tests**

```python
@pytest.mark.parametrize(("mode", "gate", "state"), [
    (ApprovalMode.MANUAL, GateStatus.PASS, StageRunState.WAITING_APPROVAL),
    (ApprovalMode.MANUAL, GateStatus.WARNING, StageRunState.WAITING_APPROVAL),
    (ApprovalMode.AUTONOMOUS, GateStatus.PASS, StageRunState.HANDOFF_READY),
    (ApprovalMode.AUTONOMOUS, GateStatus.WARNING, StageRunState.WARNING_BLOCKED),
    (ApprovalMode.AUTONOMOUS, GateStatus.NEEDS_FIX, StageRunState.NEEDS_FIX),
    (ApprovalMode.AUTONOMOUS, GateStatus.FAIL, StageRunState.FAILED),
])
def test_gate_mode_matrix(mode, gate, state) -> None:
    assert next_state(mode, gate) is state
```

- [ ] **Step 2: Implement approvals**

Approvals exist only in MANUAL. User decision is approve or rewrite/reject with feedback. Approval references exact GateRun, Artifact versions and Checkpoint root hash; any change invalidates it. API/model cannot synthesize an approval.

- [ ] **Step 3: Implement autonomous Warning choices**

WARNING creates no Handoff and offers only `rewrite`, `open_room`, `abandon`. There is no ignore/continue. Rewrite creates a recorded RevisionRequest with Warning evidence, runs a new task, P2R and Gate. Count is unbounded; identical repeated warning emits a no-progress notice but still waits for the user.

- [ ] **Step 4: Verify and commit**

```powershell
uv run alembic upgrade head
uv run pytest tests/integration/test_gate_decisions.py -v
git add backend/src/agent_platform/application/stages backend/src/agent_platform/infrastructure/database/approval_models.py backend/migrations/versions/0009_approvals_handoffs.py backend/tests/integration/test_gate_decisions.py
git commit -m "feat: apply manual and autonomous gate rules"
```

### Task 7: Immutable HandoffPacket Creation and Validation

**Files:**
- Create: `backend/src/agent_platform/domain/handoffs/models.py`
- Create: `backend/src/agent_platform/domain/handoffs/validation.py`
- Create: `backend/src/agent_platform/application/handoffs/service.py`
- Test: `backend/tests/unit/test_handoff_validation.py`
- Test: `backend/tests/integration/test_handoff_service.py`

- [ ] **Step 1: Write failing hash and isolation tests**

```python
def test_handoff_hash_is_stable_for_canonical_json() -> None:
    packet = make_handoff(approved_decisions=[{"b": 2, "a": 1}])
    assert packet.content_hash == canonical_hash(packet.without_hash())


def test_handoff_does_not_contain_chat_or_credentials() -> None:
    serialized = make_handoff().model_dump_json()
    assert "messages" not in serialized
    assert "credential_ref" not in serialized
    assert "api_key" not in serialized
```

- [ ] **Step 2: Implement exact protocol objects**

Implement `HandoffPacket`, `ProjectCheckpointRef`, `DeliverableRef` and statuses from `docs/07-handoff-protocol.md`. Normalize project-relative paths and canonicalize JSON with sorted keys and compact separators before SHA-256.

- [ ] **Step 3: Implement creation transaction**

Validate source completed, stage order, pinned Contract/RoleCard, checkpoint root, artifact hashes, Gate, MANUAL approval, and no external conflict. In one UnitOfWork lock deliverable versions, insert packet, bind source output/target input handoff, complete source, unlock target, append `handoff.created` and outbox. Target receives only allowed files, decisions, acceptance, risks and formal references—not upstream chat/drafts/reviewer internals.

- [ ] **Step 4: Implement invalidation**

Artifact/checkpoint changes, reopen, ChangeRequest or owned external changes set old packet `invalidated`; replacement sets it `superseded`. History is retained and an invalid packet cannot be consumed twice.

- [ ] **Step 5: Verify and commit**

```powershell
uv run pytest tests/unit/test_handoff_validation.py tests/integration/test_handoff_service.py -v
git add backend/src/agent_platform/domain/handoffs backend/src/agent_platform/application/handoffs/service.py backend/tests/unit/test_handoff_validation.py backend/tests/integration/test_handoff_service.py
git commit -m "feat: create verified stage handoffs"
```

### Task 8: Structured ChangeRequest Routing and Downstream Invalidation

**Files:**
- Create: `backend/src/agent_platform/domain/handoffs/change_requests.py`
- Create: `backend/src/agent_platform/application/handoffs/change_request_service.py`
- Test: `backend/tests/unit/test_change_request_routing.py`
- Test: `backend/tests/integration/test_change_request_rework.py`

- [ ] **Step 1: Write route tests**

```python
@pytest.mark.parametrize(("issue_type", "target"), [
    (IssueType.REQUIREMENT, Stage.PLANNER),
    (IssueType.ARCHITECTURE, Stage.DESIGNER),
    (IssueType.IMPLEMENTATION, Stage.BUILDER),
    (IssueType.REVIEW_VERDICT, Stage.REVIEWER),
    (IssueType.DEPLOYMENT, Stage.DEPLOYER),
])
def test_issue_routes_to_owner(issue_type, target) -> None:
    assert target_stage_for(issue_type) is target
```

- [ ] **Step 2: Implement request schema and validation**

Include all fields/statuses from `docs/07-handoff-protocol.md`. Source may target legal upstream/current owner only; evidence, affected requirements/artifacts/files and requested changes are required for blocking severity. Models cannot directly set validated/applied/resolved.

- [ ] **Step 3: Implement rework transaction**

Orchestrator validates, calculates earliest stage, creates a new StageRun, invalidates target/downstream packets and current results, locks downstream rooms, supplies structured revision feedback, and emits events. After revised handoff is consumed, mark request resolved; never edit old artifact versions.

- [ ] **Step 4: Verify and commit**

```powershell
uv run pytest tests/unit/test_change_request_routing.py tests/integration/test_change_request_rework.py -v
git add backend/src/agent_platform/domain/handoffs/change_requests.py backend/src/agent_platform/application/handoffs/change_request_service.py backend/tests/unit/test_change_request_routing.py backend/tests/integration/test_change_request_rework.py
git commit -m "feat: route structured stage rework"
```

### Task 9: Completion, Gate, Approval, Artifact and Handoff APIs

**Files:**
- Create: `backend/src/agent_platform/application/stages/completion_service.py`
- Create: `backend/src/agent_platform/interfaces/api/routes/gates.py`
- Create: `backend/src/agent_platform/interfaces/api/routes/approvals.py`
- Create: `backend/src/agent_platform/interfaces/api/routes/handoffs.py`
- Create: `backend/src/agent_platform/interfaces/api/routes/change_requests.py`
- Create: `backend/src/agent_platform/interfaces/api/routes/artifacts.py`
- Test: `backend/tests/e2e/test_fake_five_stage_workflow.py`

- [ ] **Step 1: Write a full Fake Workflow test**

Start a healthy project, complete Planner/Designer/Builder/Reviewer/Deployer with scripted artifacts and command evidence. In MANUAL, assert every PASS waits for approval. In AUTONOMOUS, assert PASS hands off automatically, WARNING blocks for rewrite/open_room/abandon, Reviewer NEEDS_FIX routes Builder, and only Reviewer PASS unlocks Deployer.

- [ ] **Step 2: Implement the atomic completion command**

One UnitOfWork validates authoritative StageRun, saves Artifact versions, creates Checkpoint, runs Gate, applies mode decision, optionally creates Approval/Handoff, updates Workflow/Stage/Room, and appends EventLog/Outbox. Any exception rolls back every row and leaves files as non-formal drafts.

- [ ] **Step 3: Implement read/decision APIs**

Expose exact Gate, Approval, ChangeRequest, Handoff, Artifact and Checkpoint endpoints from `docs/10-api-and-events.md`. Handoff has no POST/PATCH. Decisions require Idempotency-Key. Content API verifies stored Hash before returning bytes.

- [ ] **Step 4: Run full gates**

```powershell
uv run pytest tests/e2e/test_fake_five_stage_workflow.py -v
uv run pytest tests/unit tests/integration tests/contract tests/e2e -v
uv run ruff format --check .
uv run ruff check .
uv run mypy src
```

- [ ] **Step 5: Commit**

```powershell
git add backend/src/agent_platform/application/stages/completion_service.py backend/src/agent_platform/interfaces/api backend/tests/e2e/test_fake_five_stage_workflow.py
git commit -m "feat: complete verified stage handoffs"
```

## Definition of Done

- 五个 StageContract 和角色卡版本在 Workflow 创建时固定，提示词不能改变权限。
- 正式 Deliverable 必须引用真实 Artifact versions、P2R、Gate 和 ProjectCheckpoint。
- AUTONOMOUS Warning 必然阻断且只能重写、进入聊天室或放弃；没有忽略继续。
- MANUAL 每阶段等待用户审批；CapabilityRequest 仍由工具计划独立处理。
- 下游无法修改上游，只能创建 ChangeRequest；返工保留所有旧版本并准确失效下游。
