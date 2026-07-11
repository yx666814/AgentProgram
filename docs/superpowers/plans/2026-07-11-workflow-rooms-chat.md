# Workflow, Rooms and Persistent Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现固定五阶段工作流、隔离聊天室、不可变消息、单 Primary Task 队列、阶段重开以及可重放的桌面事件流。

**Architecture:** 状态转换只存在于领域对象和 Application Command。SQLite 约束保证一个项目最多一个活动工作流、一个 Room 最多一个活动任务；事件先与状态同事务持久化，再由 Outbox 广播给 WebSocket。

**Tech Stack:** Python 3.12, FastAPI, WebSocket, Pydantic v2, SQLAlchemy Async, SQLite, asyncio, pytest.

---

## File Map

```text
backend/src/agent_platform/
├─ domain/workflows/{models.py,state_machine.py,commands.py}
├─ domain/chat/{models.py,rules.py}
├─ application/workflows/{service.py,reopen_service.py}
├─ application/chat/{message_service.py,task_queue_service.py}
├─ application/events/{hub.py,outbox_dispatcher.py,tickets.py}
├─ infrastructure/database/{workflow_models.py,workflow_repositories.py}
└─ interfaces/api/routes/{workflows.py,rooms.py,tasks.py,events.py}
```

### Task 1: Workflow, StageRun, Room, Message and Task Schema

**Files:**
- Create: `backend/src/agent_platform/domain/workflows/models.py`
- Create: `backend/src/agent_platform/domain/chat/models.py`
- Create: `backend/src/agent_platform/infrastructure/database/workflow_models.py`
- Create: `backend/src/agent_platform/infrastructure/database/workflow_repositories.py`
- Create: `backend/migrations/versions/0005_workflow_chat.py`
- Test: `backend/tests/integration/test_workflow_constraints.py`

- [ ] **Step 1: Write failing database constraint tests**

```python
@pytest.mark.asyncio
async def test_project_has_only_one_active_workflow(repository: WorkflowRepository) -> None:
    await repository.add(make_workflow("wf_1", state=WorkflowState.RUNNING))
    with pytest.raises(IntegrityError):
        await repository.add(make_workflow("wf_2", state=WorkflowState.RUNNING))


@pytest.mark.asyncio
async def test_room_has_unique_message_sequence_and_one_active_task(repository: ChatRepository) -> None:
    await repository.add_message(make_message("msg_1", sequence=1))
    with pytest.raises(IntegrityError):
        await repository.add_message(make_message("msg_2", sequence=1))
    await repository.add_task(make_task("task_1", state=TaskState.RUNNING))
    with pytest.raises(IntegrityError):
        await repository.add_task(make_task("task_2", state=TaskState.RUNNING))
```

- [ ] **Step 2: Define stable enums and records**

```python
class Stage(StrEnum):
    PLANNER = "planner"
    DESIGNER = "designer"
    BUILDER = "builder"
    REVIEWER = "reviewer"
    DEPLOYER = "deployer"

STAGE_ORDER = (Stage.PLANNER, Stage.DESIGNER, Stage.BUILDER, Stage.REVIEWER, Stage.DEPLOYER)


class ApprovalMode(StrEnum):
    MANUAL = "manual"
    AUTONOMOUS = "autonomous"


class WorkflowState(StrEnum):
    CREATED = "created"
    PREFLIGHT_FAILED = "preflight_failed"
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    WARNING_BLOCKED = "warning_blocked"
    PAUSED = "paused"
    EXTERNAL_CONFLICT = "external_conflict"
    INTERRUPTED = "interrupted"
    FAILED = "failed"
    STOPPED = "stopped"
    ABANDONED = "abandoned"
    COMPLETED = "completed"
```

Define every StageRun/Room/Task state exactly as `docs/13-workflow-recovery.md`; `Message` is frozen and includes `correction_of_id`, `is_pinned`, `is_hidden_in_ui`, and `post_completion_consultation`.

- [ ] **Step 3: Add schema and partial unique indexes**

Create all tables from sections 4 and 6 of `docs/09-data-model.md`. Use partial unique indexes for active workflows and active tasks, unique `(room_id, sequence)`, unique `(workflow_id, stage, run_number)`, and integer `version` columns for command concurrency.

- [ ] **Step 4: Verify migration and repositories**

```powershell
uv run alembic upgrade head
uv run pytest tests/integration/test_workflow_constraints.py -v
```

- [ ] **Step 5: Commit**

```powershell
git add backend/src/agent_platform/domain/workflows backend/src/agent_platform/domain/chat backend/src/agent_platform/infrastructure/database backend/migrations/versions/0005_workflow_chat.py backend/tests/integration/test_workflow_constraints.py
git commit -m "feat: persist workflow rooms and chat"
```

### Task 2: Deterministic Workflow and Stage State Machines

**Files:**
- Create: `backend/src/agent_platform/domain/workflows/state_machine.py`
- Test: `backend/tests/unit/test_workflow_state_machine.py`
- Test: `backend/tests/unit/test_stage_state_machine.py`

- [ ] **Step 1: Write transition table tests**

```python
@pytest.mark.parametrize(("current", "command", "expected"), [
    (WorkflowState.CREATED, WorkflowCommand.START, WorkflowState.RUNNING),
    (WorkflowState.RUNNING, WorkflowCommand.PAUSE_COMPLETE, WorkflowState.PAUSED),
    (WorkflowState.PAUSED, WorkflowCommand.RESUME, WorkflowState.RUNNING),
    (WorkflowState.WARNING_BLOCKED, WorkflowCommand.ABANDON, WorkflowState.ABANDONED),
])
def test_allowed_workflow_transitions(current, command, expected) -> None:
    assert transition_workflow(current, command) is expected


def test_completed_workflow_cannot_resume() -> None:
    with pytest.raises(DomainError, match="cannot transition"):
        transition_workflow(WorkflowState.COMPLETED, WorkflowCommand.RESUME)
```

- [ ] **Step 2: Implement explicit maps**

`transition_workflow()` and `transition_stage()` are pure functions backed by dictionaries of `(state, command) -> state`. Missing pairs raise `workflow.invalid_state` or `stage.invalid_state`. No API, Worker payload or model result can assign state strings directly.

- [ ] **Step 3: Cover the full lifecycle**

Tests cover `LOCKED → READY → DISCUSSING → PRODUCING → P2R_REVIEWING → QUALITY_CHECKING → WAITING_APPROVAL/HANDOFF_READY → COMPLETED` and every exceptional state. Only valid upstream handoff unlocks a stage.

- [ ] **Step 4: Run tests and commit**

```powershell
uv run pytest tests/unit/test_workflow_state_machine.py tests/unit/test_stage_state_machine.py -v
git add backend/src/agent_platform/domain/workflows/state_machine.py backend/tests/unit/test_workflow_state_machine.py backend/tests/unit/test_stage_state_machine.py
git commit -m "feat: enforce workflow state transitions"
```

### Task 3: Workflow Creation, Start and Approval Modes

**Files:**
- Create: `backend/src/agent_platform/domain/workflows/commands.py`
- Create: `backend/src/agent_platform/application/workflows/service.py`
- Test: `backend/tests/integration/test_workflow_service.py`

- [ ] **Step 1: Write failing start/idempotency tests**

```python
@pytest.mark.asyncio
async def test_create_builds_five_isolated_rooms(service: WorkflowService) -> None:
    workflow = await service.create("project_1", ApprovalMode.MANUAL, "idem-1")
    assert [room.stage for room in workflow.rooms] == list(STAGE_ORDER)
    assert workflow.rooms[0].state is RoomState.READY
    assert all(room.state is RoomState.LOCKED for room in workflow.rooms[1:])


@pytest.mark.asyncio
async def test_repeated_start_returns_same_result(service: WorkflowService) -> None:
    first = await service.start("wf_1", idempotency_key="same")
    second = await service.start("wf_1", idempotency_key="same")
    assert second.command_result_id == first.command_result_id
```

- [ ] **Step 2: Implement project-scoped command locking**

Use one `asyncio.Lock` per project plus expected database version. `create()` pins `contract_set_version` and `role_card_set_version`, creates five Rooms and the first Planner StageRun in one UnitOfWork. `start()` runs Project Preflight, refuses an existing active workflow, obtains a Worker, updates state, and appends `workflow.started` atomically. Store idempotency key, request fingerprint and serialized result; same key with different body raises `request.idempotency_conflict`.

- [ ] **Step 3: Implement approval-mode change rule**

Only paused workflows may switch `manual ↔ autonomous`. The command records old/new mode and `workflow.approval_mode_changed`; it does not retroactively remove an already-created Approval or CapabilityRequest.

- [ ] **Step 4: Verify and commit**

```powershell
uv run pytest tests/integration/test_workflow_service.py -v
git add backend/src/agent_platform/domain/workflows/commands.py backend/src/agent_platform/application/workflows/service.py backend/tests/integration/test_workflow_service.py
git commit -m "feat: create and start five stage workflows"
```

### Task 4: Immutable Messages, Corrections, Pins and Hide Rules

**Files:**
- Create: `backend/src/agent_platform/domain/chat/rules.py`
- Create: `backend/src/agent_platform/application/chat/message_service.py`
- Test: `backend/tests/unit/test_message_rules.py`
- Test: `backend/tests/integration/test_message_service.py`

- [ ] **Step 1: Write failing message tests**

```python
def test_correction_creates_new_message() -> None:
    original = make_message(id="msg_1", content="old")
    corrected = correct_message(original, new_id="msg_2", content="new", sequence=2)
    assert original.content == "old"
    assert corrected.correction_of_id == "msg_1"


def test_formal_evidence_message_cannot_be_hidden() -> None:
    with pytest.raises(DomainError) as error:
        ensure_can_hide(make_message(id="msg_1"), referenced_by_formal_record=True)
    assert error.value.code == "message.hide_forbidden"
```

- [ ] **Step 2: Implement append-only behavior**

There is no repository update method for `content`, `sender`, `sequence`, `reply_to_id`, or `correction_of_id`. Correction appends a new user message and emits `message.corrected`. Pin/unpin and UI hide are separate audit commands; hide is rejected when a message is referenced by a Decision, Artifact, Gate, ChangeRequest or Handoff.

- [ ] **Step 3: Allocate sequence transactionally**

Within the Room row lock/version update, calculate `next_sequence = last_sequence + 1`, insert Message and EventLog, then commit. A unique collision retries the transaction once and never renumbers existing messages.

- [ ] **Step 4: Verify and commit**

```powershell
uv run pytest tests/unit/test_message_rules.py tests/integration/test_message_service.py -v
git add backend/src/agent_platform/domain/chat/rules.py backend/src/agent_platform/application/chat/message_service.py backend/tests/unit/test_message_rules.py backend/tests/integration/test_message_service.py
git commit -m "feat: preserve immutable room messages"
```

### Task 5: One Active Primary Task and FIFO Message Queue

**Files:**
- Create: `backend/src/agent_platform/application/chat/task_queue_service.py`
- Test: `backend/tests/integration/test_room_task_queue.py`

- [ ] **Step 1: Write failing queue tests**

```python
@pytest.mark.asyncio
async def test_message_during_task_is_queued_not_injected(service: TaskQueueService) -> None:
    active = await service.start_for_message("room_1", "msg_1")
    queued = await service.start_for_message("room_1", "msg_2")
    assert active.state is TaskState.RUNNING
    assert queued.state is TaskState.QUEUED
    assert queued.queued_message_id == "msg_2"


@pytest.mark.asyncio
async def test_completion_starts_next_message_in_fifo_order(service: TaskQueueService) -> None:
    await service.complete("task_1")
    assert (await service.get_active("room_1")).queued_message_id == "msg_2"
```

- [ ] **Step 2: Implement queue commands**

`start_for_message()` checks Room state and active task in one UnitOfWork. If active, it inserts `queued` Task and emits `task.queued`; otherwise it inserts `running`, binds current Worker, and emits `task.started`. Completion/cancel/failure persists terminal state before atomically claiming the oldest queued task by created_at/id. Deleting a queue item is allowed only while still queued.

- [ ] **Step 3: Verify concurrency**

Run two concurrent `start_for_message()` calls 100 times; assert exactly one running task and one queued task each time.

```powershell
uv run pytest tests/integration/test_room_task_queue.py -v
```

- [ ] **Step 4: Commit**

```powershell
git add backend/src/agent_platform/application/chat/task_queue_service.py backend/tests/integration/test_room_task_queue.py
git commit -m "feat: serialize primary room tasks"
```

### Task 6: Completed Consultation and Explicit Stage Reopen

**Files:**
- Create: `backend/src/agent_platform/application/workflows/reopen_service.py`
- Test: `backend/tests/integration/test_stage_reopen.py`

- [ ] **Step 1: Write failing consultation/reopen tests**

```python
@pytest.mark.asyncio
async def test_consultation_is_read_only(service: ReopenService) -> None:
    consultation = await service.start_consultation("planner_room")
    assert consultation.tools_enabled is False
    assert consultation.message_type == "post_completion_consultation"


@pytest.mark.asyncio
async def test_reopen_creates_new_run_and_invalidates_downstream(service: ReopenService) -> None:
    result = await service.reopen("wf_1", Stage.DESIGNER, reason="API changed")
    assert result.new_stage_run.run_number == 2
    assert result.invalidated_stages == (Stage.DESIGNER, Stage.BUILDER, Stage.REVIEWER, Stage.DEPLOYER)
```

- [ ] **Step 2: Implement consultation boundary**

Consultation creates a P0 task marked read-only. Its runtime grant contains no tool catalog, cannot create formal Artifact/Decision/ChangeRequest, and cannot update StageRun state.

- [ ] **Step 3: Implement reopen transaction**

Explicit reopen creates a new StageRun, changes target Room from consultation/completed to ready, invalidates target and downstream handoffs, checkpoints, approvals and current artifacts without deleting them, locks downstream rooms, and emits `stage.reopened` plus individual invalidation events.

- [ ] **Step 4: Verify and commit**

```powershell
uv run pytest tests/integration/test_stage_reopen.py -v
git add backend/src/agent_platform/application/workflows/reopen_service.py backend/tests/integration/test_stage_reopen.py
git commit -m "feat: support consultation and explicit reopen"
```

### Task 7: Transactional Event Hub, WebSocket Tickets and Replay

**Files:**
- Create: `backend/src/agent_platform/application/events/hub.py`
- Create: `backend/src/agent_platform/application/events/outbox_dispatcher.py`
- Create: `backend/src/agent_platform/application/events/tickets.py`
- Create: `backend/src/agent_platform/interfaces/api/routes/events.py`
- Test: `backend/tests/contract/test_websocket_events.py`

- [ ] **Step 1: Write failing ticket/replay tests**

```python
def test_ticket_is_single_use_and_expires(ticket_service: TicketService, clock: FakeClock) -> None:
    ticket = ticket_service.issue(session_id="session_1")
    assert ticket_service.consume(ticket.value, "session_1") is True
    assert ticket_service.consume(ticket.value, "session_1") is False
    expired = ticket_service.issue("session_1")
    clock.advance(seconds=31)
    assert ticket_service.consume(expired.value, "session_1") is False
```

WebSocket tests create events 10–12, connect with `after=10`, receive 11 and 12 in order, disconnect, create 13, reconnect with `after=12`, and receive only 13.

- [ ] **Step 2: Implement event envelopes and dispatcher**

Only committed EventLog rows become:

```python
class EventEnvelope(BaseModel):
    schema_version: Literal[1] = 1
    event_id: int
    event_type: str
    project_id: str | None
    workflow_id: str | None
    room_id: str | None
    task_id: str | None
    timestamp: datetime
    payload: dict[str, Any]
```

Dispatcher polls undelivered outbox rows, publishes to in-memory subscribers, then marks delivered. Replay reads EventLog by monotonic `event_id`; transient `model.delta` may broadcast without durable token chunks, but final `message.created` is durable.

- [ ] **Step 3: Implement authenticated WebSocket**

`POST /api/v1/auth/ws-ticket` requires Bearer auth. `/api/v1/events` validates loopback Origin, session, one-time 30-second ticket and non-negative `after`; it replays first, then subscribes without a gap by using a high-water event id.

- [ ] **Step 4: Run WebSocket tests**

```powershell
uv run pytest tests/contract/test_websocket_events.py -v
```

- [ ] **Step 5: Commit**

```powershell
git add backend/src/agent_platform/application/events backend/src/agent_platform/interfaces/api/routes/events.py backend/tests/contract/test_websocket_events.py
git commit -m "feat: replay committed workflow events"
```

### Task 8: Workflow, Room, Message and Task REST API

**Files:**
- Create: `backend/src/agent_platform/interfaces/api/routes/workflows.py`
- Create: `backend/src/agent_platform/interfaces/api/routes/rooms.py`
- Create: `backend/src/agent_platform/interfaces/api/routes/tasks.py`
- Create: `backend/src/agent_platform/interfaces/api/schemas/workflows.py`
- Test: `backend/tests/contract/test_workflow_chat_api.py`

- [ ] **Step 1: Write API tests for all state-changing commands**

Cover workflow create/get/start/pause/resume/stop/abandon/mode-change, stage list/get/rewrite/open-room/reopen, room list/get/messages/consultation, message create/correct/pin/unpin/hide, task get/cancel and queue list/delete. Assert no Message PATCH route exists.

- [ ] **Step 2: Implement thin routes**

Every command requires `Idempotency-Key`; every versioned update requires expected version/ETag. Routes call application services and convert domain DTOs to response schemas. They never mutate ORM rows or trust Worker state. Cursor pagination uses `after=<sequence>&limit<=200`.

- [ ] **Step 3: Run contract and plan-wide tests**

```powershell
uv run pytest tests/contract/test_workflow_chat_api.py tests/contract/test_websocket_events.py -v
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest tests/unit tests/integration tests/contract -v
```

- [ ] **Step 4: Commit**

```powershell
git add backend/src/agent_platform/interfaces/api backend/tests/contract/test_workflow_chat_api.py
git commit -m "feat: expose workflow and chat api"
```

## Definition of Done

- 五个 Room 始终隔离，只有有效交接才能解锁下一 Room。
- 消息正文永不覆盖；更正是新消息；正式证据不能隐藏。
- 一个 Room 永远只有一个活动 Primary Task，运行中消息严格排队。
- Completed Room 只能无工具咨询，修改必须显式 Reopen 并使下游失效。
- WebSocket 只广播已提交事件，断线后可按 `event_id` 重放和去重。
