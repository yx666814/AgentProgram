from __future__ import annotations

from copy import deepcopy
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_platform.domain.contracts import STAGE_ORDER, Stage, StageRunState
from agent_platform.domain.governance import ExecutionMode
from agent_platform.domain.shared.errors import DomainError, ErrorCategory
from agent_platform.domain.workflows import (
    Message,
    MessageAuthor,
    MessageKind,
    Room,
    RoomStatus,
    StageRun,
    TaskStatus,
    Workflow,
    WorkflowSnapshot,
    WorkflowStatus,
    WorkflowTask,
)
from agent_platform.infrastructure.database.models import (
    MessageRow,
    RoomRow,
    StageRunRow,
    WorkflowRow,
    WorkflowTaskRow,
)

_ACTIVE_WORKFLOW_STATUSES = tuple(
    status.value
    for status in WorkflowStatus
    if status
    not in {
        WorkflowStatus.FAILED,
        WorkflowStatus.STOPPED,
        WorkflowStatus.ABANDONED,
        WorkflowStatus.COMPLETED,
    }
)


class SqlAlchemyWorkflowRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_graph(
        self,
        workflow: Workflow,
        stage_runs: tuple[StageRun, ...],
        rooms: tuple[Room, ...],
    ) -> None:
        self._session.add(_workflow_row(workflow))
        await self._session.flush()
        self._session.add_all(_stage_run_row(run) for run in stage_runs)
        await self._session.flush()
        self._session.add_all(_room_row(room) for room in rooms)
        await self._session.flush()

    async def get(self, workflow_id: str) -> Workflow | None:
        row = await self._session.get(WorkflowRow, workflow_id)
        return _workflow_from_row(row) if row is not None else None

    async def list_for_project(self, project_id: str) -> tuple[Workflow, ...]:
        statement = (
            select(WorkflowRow)
            .where(WorkflowRow.project_id == project_id)
            .order_by(WorkflowRow.updated_at.desc(), WorkflowRow.id)
        )
        rows = (await self._session.scalars(statement)).all()
        return tuple(_workflow_from_row(row) for row in rows)

    async def find_active_for_project(self, project_id: str) -> Workflow | None:
        statement = (
            select(WorkflowRow)
            .where(
                WorkflowRow.project_id == project_id,
                WorkflowRow.status.in_(_ACTIVE_WORKFLOW_STATUSES),
            )
            .order_by(WorkflowRow.created_at.desc(), WorkflowRow.id)
            .limit(1)
        )
        row = await self._session.scalar(statement)
        return _workflow_from_row(row) if row is not None else None

    async def get_snapshot(self, workflow_id: str) -> WorkflowSnapshot | None:
        workflow_row = await self._session.get(WorkflowRow, workflow_id)
        if workflow_row is None:
            return None
        runs = await self._current_stage_run_rows(workflow_id)
        run_ids = tuple(run.id for run in runs)
        rooms: tuple[RoomRow, ...] = ()
        if run_ids:
            statement = select(RoomRow).where(RoomRow.stage_run_id.in_(run_ids))
            room_rows = (await self._session.scalars(statement)).all()
            room_by_run = {room.stage_run_id: room for room in room_rows}
            rooms = tuple(room_by_run[run.id] for run in runs)
        return WorkflowSnapshot(
            schema_version=1,
            workflow=_workflow_from_row(workflow_row),
            stage_runs=tuple(_stage_run_from_row(run) for run in runs),
            rooms=tuple(_room_from_row(room) for room in rooms),
        )

    async def list_stage_run_history(self, workflow_id: str) -> tuple[StageRun, ...]:
        statement = (
            select(StageRunRow)
            .where(StageRunRow.workflow_id == workflow_id)
            .order_by(StageRunRow.created_at, StageRunRow.id)
        )
        rows = (await self._session.scalars(statement)).all()
        return tuple(_stage_run_from_row(row) for row in rows)

    async def get_stage_run(self, stage_run_id: str) -> StageRun | None:
        row = await self._session.get(StageRunRow, stage_run_id)
        return _stage_run_from_row(row) if row is not None else None

    async def get_current_stage_run(
        self,
        workflow_id: str,
        stage: Stage,
    ) -> StageRun | None:
        row = await self._current_stage_run_row(workflow_id, stage)
        return _stage_run_from_row(row) if row is not None else None

    async def get_room(self, room_id: str) -> Room | None:
        row = await self._session.get(RoomRow, room_id)
        return _room_from_row(row) if row is not None else None

    async def get_room_for_stage_run(self, stage_run_id: str) -> Room | None:
        statement = select(RoomRow).where(RoomRow.stage_run_id == stage_run_id)
        row = await self._session.scalar(statement)
        return _room_from_row(row) if row is not None else None

    async def start_workflow(
        self,
        workflow_id: str,
        *,
        expected_version: int,
        updated_at: datetime,
    ) -> Workflow:
        row = await self._require_workflow_row(workflow_id)
        _require_version("workflow", row.version, expected_version)
        if WorkflowStatus(row.status) is not WorkflowStatus.CREATED:
            raise DomainError(
                code="workflow.already_started",
                message="Workflow can only be started once",
                category=ErrorCategory.CONFLICT,
            )
        row.status = WorkflowStatus.RUNNING.value
        row.version += 1
        row.updated_at = updated_at
        await self._session.flush()
        return _workflow_from_row(row)

    async def transition_stage(
        self,
        workflow_id: str,
        stage_run_id: str,
        target: StageRunState,
        *,
        expected_workflow_version: int,
        expected_stage_version: int,
        updated_at: datetime,
    ) -> tuple[Workflow, StageRun, StageRun | None]:
        workflow = await self._require_workflow_row(workflow_id)
        run = await self._require_stage_run_row(stage_run_id)
        if run.workflow_id != workflow_id:
            raise _not_found("stage_run", "Stage run was not found")
        _require_version("workflow", workflow.version, expected_workflow_version)
        _require_version("stage_run", run.version, expected_stage_version)
        if WorkflowStatus(workflow.status) is not WorkflowStatus.RUNNING:
            raise DomainError(
                code="workflow.not_running",
                message="Workflow is not running",
                category=ErrorCategory.CONFLICT,
            )
        if workflow.current_stage != run.stage:
            raise DomainError(
                code="stage_run.not_current",
                message="Only the current stage can transition",
                category=ErrorCategory.CONFLICT,
            )
        current = StageRunState(run.state)
        if current is StageRunState.LOCKED:
            raise DomainError(
                code="stage_run.locked",
                message="Stage run is locked",
                category=ErrorCategory.CONFLICT,
            )
        if current is StageRunState.READY and target is StageRunState.DISCUSSING:
            run.started_at = updated_at
        run.state = target.value
        run.version += 1
        unlocked: StageRunRow | None = None
        room = await self._require_room_for_stage_run_row(run.id)
        if target is StageRunState.COMPLETED:
            run.completed_at = updated_at
            room.status = RoomStatus.CONSULTATION.value
            room.version += 1
            room.updated_at = updated_at
            next_stage = _successor(Stage(run.stage))
            if next_stage is None:
                workflow.status = WorkflowStatus.COMPLETED.value
            else:
                unlocked = await self._current_stage_run_row(workflow_id, next_stage)
                if unlocked is None or StageRunState(unlocked.state) is not StageRunState.LOCKED:
                    raise RuntimeError("next stage run is missing or not locked")
                unlocked.state = StageRunState.READY.value
                unlocked.version += 1
                workflow.current_stage = next_stage.value
        elif target in {
            StageRunState.FAILED,
            StageRunState.CANCELLED,
            StageRunState.ABANDONED,
        }:
            workflow.status = (
                WorkflowStatus.ABANDONED.value
                if target is StageRunState.ABANDONED
                else WorkflowStatus.FAILED.value
            )
            room.status = RoomStatus.ARCHIVED.value
            room.version += 1
            room.updated_at = updated_at
        workflow.version += 1
        workflow.updated_at = updated_at
        await self._session.flush()
        return (
            _workflow_from_row(workflow),
            _stage_run_from_row(run),
            _stage_run_from_row(unlocked) if unlocked is not None else None,
        )

    async def reopen_stage(
        self,
        workflow_id: str,
        stage: Stage,
        new_runs: tuple[StageRun, ...],
        new_rooms: tuple[Room, ...],
        *,
        expected_workflow_version: int,
        updated_at: datetime,
    ) -> WorkflowSnapshot:
        workflow = await self._require_workflow_row(workflow_id)
        _require_version("workflow", workflow.version, expected_workflow_version)
        current_rows = await self._current_stage_run_rows(workflow_id)
        by_stage = {Stage(row.stage): row for row in current_rows}
        target = by_stage.get(stage)
        if target is None or StageRunState(target.state) is not StageRunState.COMPLETED:
            raise DomainError(
                code="stage_run.reopen_requires_completion",
                message="Only a completed stage can be reopened",
                category=ErrorCategory.CONFLICT,
            )
        affected = set(STAGE_ORDER[STAGE_ORDER.index(stage) :])
        affected_run_ids = tuple(row.id for member, row in by_stage.items() if member in affected)
        room_statement = select(RoomRow).where(RoomRow.stage_run_id.in_(affected_run_ids))
        old_rooms = (await self._session.scalars(room_statement)).all()
        for room in old_rooms:
            room.status = RoomStatus.ARCHIVED.value
            room.version += 1
            room.updated_at = updated_at
        task_statement = select(WorkflowTaskRow).where(
            WorkflowTaskRow.stage_run_id.in_(affected_run_ids),
            WorkflowTaskRow.status.in_((TaskStatus.QUEUED.value, TaskStatus.RUNNING.value)),
        )
        pending_tasks = (await self._session.scalars(task_statement)).all()
        for task in pending_tasks:
            task.status = TaskStatus.CANCELLED.value
            task.version += 1
            task.completed_at = updated_at
        self._session.add_all(_stage_run_row(run) for run in new_runs)
        await self._session.flush()
        self._session.add_all(_room_row(room) for room in new_rooms)
        workflow.status = WorkflowStatus.RUNNING.value
        workflow.current_stage = stage.value
        workflow.version += 1
        workflow.updated_at = updated_at
        await self._session.flush()
        snapshot = await self.get_snapshot(workflow_id)
        if snapshot is None:
            raise RuntimeError("workflow disappeared after reopening")
        return snapshot

    async def append_message(
        self,
        message: Message,
        *,
        expected_room_version: int,
        updated_at: datetime,
    ) -> Room:
        room = await self._require_room_row(message.room_id)
        _require_version("room", room.version, expected_room_version)
        status = RoomStatus(room.status)
        if status is RoomStatus.ARCHIVED:
            raise DomainError(
                code="room.archived",
                message="Archived rooms are read-only",
                category=ErrorCategory.CONFLICT,
            )
        if message.sequence != room.next_sequence:
            raise DomainError(
                code="message.sequence_conflict",
                message="Room message sequence has changed",
                category=ErrorCategory.CONFLICT,
                details={"next_sequence": room.next_sequence},
            )
        if status is RoomStatus.CONSULTATION and message.kind not in {
            MessageKind.CONSULTATION,
            MessageKind.CORRECTION,
        }:
            raise DomainError(
                code="room.consultation_only",
                message="Completed stage rooms only accept consultation messages",
                category=ErrorCategory.CONFLICT,
            )
        if status is RoomStatus.ACTIVE and message.kind is MessageKind.CONSULTATION:
            raise DomainError(
                code="room.discussion_only",
                message="Active stage rooms accept discussion messages",
                category=ErrorCategory.CONFLICT,
            )
        if message.correction_of_id is not None:
            original = await self._session.get(MessageRow, message.correction_of_id)
            if original is None or original.room_id != message.room_id:
                raise _not_found("message", "Original message was not found in this room")
        self._session.add(_message_row(message))
        room.next_sequence += 1
        room.version += 1
        room.updated_at = updated_at
        await self._session.flush()
        return _room_from_row(room)

    async def list_messages(
        self,
        room_id: str,
        *,
        after_sequence: int,
        limit: int,
    ) -> tuple[Message, ...]:
        if await self._session.get(RoomRow, room_id) is None:
            raise _not_found("room", "Room was not found")
        statement = (
            select(MessageRow)
            .where(MessageRow.room_id == room_id, MessageRow.sequence > after_sequence)
            .order_by(MessageRow.sequence)
            .limit(limit)
        )
        rows = (await self._session.scalars(statement)).all()
        return tuple(_message_from_row(row) for row in rows)

    async def add_task(self, task: WorkflowTask) -> None:
        self._session.add(_task_row(task))
        await self._session.flush()

    async def get_task(self, task_id: str) -> WorkflowTask | None:
        row = await self._session.get(WorkflowTaskRow, task_id)
        return _task_from_row(row) if row is not None else None

    async def list_tasks(
        self,
        workflow_id: str,
        *,
        status: TaskStatus | None = None,
    ) -> tuple[WorkflowTask, ...]:
        statement = select(WorkflowTaskRow).where(WorkflowTaskRow.workflow_id == workflow_id)
        if status is not None:
            statement = statement.where(WorkflowTaskRow.status == status.value)
        statement = statement.order_by(WorkflowTaskRow.created_at, WorkflowTaskRow.id)
        rows = (await self._session.scalars(statement)).all()
        return tuple(_task_from_row(row) for row in rows)

    async def start_task(
        self,
        task_id: str,
        *,
        expected_version: int,
        started_at: datetime,
    ) -> WorkflowTask:
        task = await self._require_task_row(task_id)
        _require_version("task", task.version, expected_version)
        if TaskStatus(task.status) is not TaskStatus.QUEUED:
            raise DomainError(
                code="task.not_queued",
                message="Only queued tasks can start",
                category=ErrorCategory.CONFLICT,
            )
        running = await self._session.scalar(
            select(WorkflowTaskRow.id)
            .where(
                WorkflowTaskRow.workflow_id == task.workflow_id,
                WorkflowTaskRow.status == TaskStatus.RUNNING.value,
            )
            .limit(1)
        )
        if running is not None:
            raise DomainError(
                code="task.workflow_busy",
                message="Another workflow task is already running",
                category=ErrorCategory.CONFLICT,
            )
        first_queued = await self._session.scalar(
            select(WorkflowTaskRow.id)
            .where(
                WorkflowTaskRow.workflow_id == task.workflow_id,
                WorkflowTaskRow.status == TaskStatus.QUEUED.value,
            )
            .order_by(WorkflowTaskRow.created_at, WorkflowTaskRow.id)
            .limit(1)
        )
        if first_queued != task.id:
            raise DomainError(
                code="task.queue_order_conflict",
                message="Task is not next in the workflow queue",
                category=ErrorCategory.CONFLICT,
            )
        task.status = TaskStatus.RUNNING.value
        task.started_at = started_at
        task.version += 1
        await self._session.flush()
        return _task_from_row(task)

    async def complete_task(
        self,
        task_id: str,
        *,
        succeeded: bool,
        result: dict[str, object],
        expected_version: int,
        completed_at: datetime,
    ) -> WorkflowTask:
        task = await self._require_task_row(task_id)
        _require_version("task", task.version, expected_version)
        if TaskStatus(task.status) is not TaskStatus.RUNNING:
            raise DomainError(
                code="task.not_running",
                message="Only running tasks can complete",
                category=ErrorCategory.CONFLICT,
            )
        task.status = (TaskStatus.SUCCEEDED if succeeded else TaskStatus.FAILED).value
        task.result = deepcopy(result)
        task.completed_at = completed_at
        task.version += 1
        await self._session.flush()
        return _task_from_row(task)

    async def cancel_task(
        self,
        task_id: str,
        *,
        expected_version: int,
        completed_at: datetime,
    ) -> WorkflowTask:
        task = await self._require_task_row(task_id)
        _require_version("task", task.version, expected_version)
        if TaskStatus(task.status) not in {TaskStatus.QUEUED, TaskStatus.RUNNING}:
            raise DomainError(
                code="task.not_cancellable",
                message="Task is already terminal",
                category=ErrorCategory.CONFLICT,
            )
        task.status = TaskStatus.CANCELLED.value
        task.completed_at = completed_at
        task.version += 1
        await self._session.flush()
        return _task_from_row(task)

    async def _current_stage_run_rows(self, workflow_id: str) -> tuple[StageRunRow, ...]:
        statement = (
            select(StageRunRow)
            .where(StageRunRow.workflow_id == workflow_id)
            .order_by(StageRunRow.attempt.desc(), StageRunRow.id.desc())
        )
        rows = (await self._session.scalars(statement)).all()
        current: dict[Stage, StageRunRow] = {}
        for row in rows:
            current.setdefault(Stage(row.stage), row)
        return tuple(current[stage] for stage in STAGE_ORDER if stage in current)

    async def _current_stage_run_row(
        self,
        workflow_id: str,
        stage: Stage,
    ) -> StageRunRow | None:
        statement = (
            select(StageRunRow)
            .where(StageRunRow.workflow_id == workflow_id, StageRunRow.stage == stage.value)
            .order_by(StageRunRow.attempt.desc(), StageRunRow.id.desc())
            .limit(1)
        )
        return (await self._session.scalars(statement)).first()

    async def _require_workflow_row(self, workflow_id: str) -> WorkflowRow:
        row = await self._session.get(WorkflowRow, workflow_id)
        if row is None:
            raise _not_found("workflow", "Workflow was not found")
        return row

    async def _require_stage_run_row(self, stage_run_id: str) -> StageRunRow:
        row = await self._session.get(StageRunRow, stage_run_id)
        if row is None:
            raise _not_found("stage_run", "Stage run was not found")
        return row

    async def _require_room_row(self, room_id: str) -> RoomRow:
        row = await self._session.get(RoomRow, room_id)
        if row is None:
            raise _not_found("room", "Room was not found")
        return row

    async def _require_room_for_stage_run_row(self, stage_run_id: str) -> RoomRow:
        statement = select(RoomRow).where(RoomRow.stage_run_id == stage_run_id)
        row = await self._session.scalar(statement)
        if row is None:
            raise RuntimeError("stage run room is missing")
        return row

    async def _require_task_row(self, task_id: str) -> WorkflowTaskRow:
        row = await self._session.get(WorkflowTaskRow, task_id)
        if row is None:
            raise _not_found("task", "Task was not found")
        return row


def _successor(stage: Stage) -> Stage | None:
    index = STAGE_ORDER.index(stage)
    return None if index == len(STAGE_ORDER) - 1 else STAGE_ORDER[index + 1]


def _require_version(entity: str, current: int, expected: int) -> None:
    if current != expected:
        raise DomainError(
            code=f"{entity}.version_conflict",
            message=f"{entity.replace('_', ' ').title()} version has changed",
            category=ErrorCategory.CONFLICT,
            details={"current_version": current},
        )


def _not_found(code: str, message: str) -> DomainError:
    return DomainError(
        code=f"{code}.not_found",
        message=message,
        category=ErrorCategory.NOT_FOUND,
    )


def _workflow_row(workflow: Workflow) -> WorkflowRow:
    return WorkflowRow(
        id=workflow.id,
        project_id=workflow.project_id,
        schema_version=workflow.schema_version,
        title=workflow.title,
        status=workflow.status.value,
        execution_mode=workflow.execution_mode.value,
        current_stage=workflow.current_stage.value,
        version=workflow.version,
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
    )


def _stage_run_row(run: StageRun) -> StageRunRow:
    return StageRunRow(
        id=run.id,
        workflow_id=run.workflow_id,
        schema_version=run.schema_version,
        stage=run.stage.value,
        attempt=run.attempt,
        state=run.state.value,
        version=run.version,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


def _room_row(room: Room) -> RoomRow:
    return RoomRow(
        id=room.id,
        workflow_id=room.workflow_id,
        stage_run_id=room.stage_run_id,
        schema_version=room.schema_version,
        stage=room.stage.value,
        status=room.status.value,
        next_sequence=room.next_sequence,
        version=room.version,
        created_at=room.created_at,
        updated_at=room.updated_at,
    )


def _message_row(message: Message) -> MessageRow:
    return MessageRow(
        id=message.id,
        room_id=message.room_id,
        schema_version=message.schema_version,
        sequence=message.sequence,
        author=message.author.value,
        kind=message.kind.value,
        content=message.content,
        correction_of_id=message.correction_of_id,
        created_at=message.created_at,
    )


def _task_row(task: WorkflowTask) -> WorkflowTaskRow:
    return WorkflowTaskRow(
        id=task.id,
        workflow_id=task.workflow_id,
        stage_run_id=task.stage_run_id,
        room_id=task.room_id,
        schema_version=task.schema_version,
        title=task.title,
        status=task.status.value,
        payload=deepcopy(task.payload),
        result=deepcopy(task.result),
        version=task.version,
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
    )


def _workflow_from_row(row: WorkflowRow) -> Workflow:
    return Workflow(
        schema_version=1,
        id=row.id,
        project_id=row.project_id,
        title=row.title,
        status=WorkflowStatus(row.status),
        execution_mode=ExecutionMode(row.execution_mode),
        current_stage=Stage(row.current_stage),
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _stage_run_from_row(row: StageRunRow) -> StageRun:
    return StageRun(
        schema_version=1,
        id=row.id,
        workflow_id=row.workflow_id,
        stage=Stage(row.stage),
        attempt=row.attempt,
        state=StageRunState(row.state),
        version=row.version,
        created_at=row.created_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


def _room_from_row(row: RoomRow) -> Room:
    return Room(
        schema_version=1,
        id=row.id,
        workflow_id=row.workflow_id,
        stage_run_id=row.stage_run_id,
        stage=Stage(row.stage),
        status=RoomStatus(row.status),
        next_sequence=row.next_sequence,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _message_from_row(row: MessageRow) -> Message:
    return Message(
        schema_version=1,
        id=row.id,
        room_id=row.room_id,
        sequence=row.sequence,
        author=MessageAuthor(row.author),
        kind=MessageKind(row.kind),
        content=row.content,
        correction_of_id=row.correction_of_id,
        created_at=row.created_at,
    )


def _task_from_row(row: WorkflowTaskRow) -> WorkflowTask:
    return WorkflowTask(
        schema_version=1,
        id=row.id,
        workflow_id=row.workflow_id,
        stage_run_id=row.stage_run_id,
        room_id=row.room_id,
        title=row.title,
        status=TaskStatus(row.status),
        payload=deepcopy(row.payload),
        result=deepcopy(row.result),
        version=row.version,
        created_at=row.created_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )
