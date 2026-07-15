from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from agent_platform.domain.contracts import STAGE_ORDER, Stage, StageRunState
from agent_platform.domain.events import ActorRef, ActorType, EventEnvelope, EventSource
from agent_platform.domain.projects import ProjectStatus
from agent_platform.domain.shared.errors import DomainError, ErrorCategory
from agent_platform.domain.shared.ids import new_id
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
    require_stage_transition,
)
from agent_platform.infrastructure.database.session import Database
from agent_platform.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from agent_platform.ports.event_publishing import LOCAL_AUDIT_CONSUMER, WEBSOCKET_CONSUMER


@dataclass(frozen=True, slots=True)
class StageTransitionExecution:
    workflow: Workflow
    stage_run: StageRun
    unlocked_stage_run: StageRun | None


@dataclass(frozen=True, slots=True)
class MessageAppendExecution:
    message: Message
    room: Room


type TaskMutation = Callable[[SqlAlchemyUnitOfWork, datetime], Awaitable[WorkflowTask]]


class WorkflowApplicationService:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def create_workflow(
        self,
        project_id: str,
        *,
        title: str,
        correlation_id: str,
    ) -> WorkflowSnapshot:
        now = datetime.now(UTC)
        workflow_id = new_id("workflow")
        workflow = Workflow(
            schema_version=1,
            id=workflow_id,
            project_id=project_id,
            title=title.strip(),
            status=WorkflowStatus.CREATED,
            current_stage=Stage.PLANNER,
            version=1,
            created_at=now,
            updated_at=now,
        )
        runs: list[StageRun] = []
        rooms: list[Room] = []
        for stage in STAGE_ORDER:
            run = StageRun(
                schema_version=1,
                id=new_id("stagerun"),
                workflow_id=workflow_id,
                stage=stage,
                attempt=1,
                state=(StageRunState.READY if stage is Stage.PLANNER else StageRunState.LOCKED),
                version=1,
                created_at=now,
            )
            room = Room(
                schema_version=1,
                id=new_id("room"),
                workflow_id=workflow_id,
                stage_run_id=run.id,
                stage=stage,
                status=RoomStatus.ACTIVE,
                next_sequence=1,
                version=1,
                created_at=now,
                updated_at=now,
            )
            runs.append(run)
            rooms.append(room)
        async with self._write_uow() as uow:
            registration = await uow.projects.get(project_id)
            if registration is None:
                raise _not_found("project", "Project was not found")
            if registration.project.status is not ProjectStatus.READY:
                raise DomainError(
                    code="workflow.project_not_ready",
                    message="Project must pass preflight before workflow creation",
                    category=ErrorCategory.CONFLICT,
                )
            active = await uow.workflows.find_active_for_project(project_id)
            if active is not None:
                raise DomainError(
                    code="workflow.active_exists",
                    message="Project already has an active workflow",
                    category=ErrorCategory.CONFLICT,
                    details={"workflow_id": active.id},
                )
            await uow.workflows.add_graph(workflow, tuple(runs), tuple(rooms))
            await _append_event(
                uow,
                event_type="workflow.created",
                correlation_id=correlation_id,
                occurred_at=now,
                project_id=project_id,
                workflow_id=workflow_id,
                payload={"title": workflow.title},
            )
            await uow.commit()
        return WorkflowSnapshot(
            schema_version=1,
            workflow=workflow,
            stage_runs=tuple(runs),
            rooms=tuple(rooms),
        )

    async def list_workflows(self, project_id: str) -> tuple[Workflow, ...]:
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            if await uow.projects.get(project_id) is None:
                raise _not_found("project", "Project was not found")
            return await uow.workflows.list_for_project(project_id)

    async def get_workflow(self, workflow_id: str) -> WorkflowSnapshot:
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            snapshot = await uow.workflows.get_snapshot(workflow_id)
        if snapshot is None:
            raise _not_found("workflow", "Workflow was not found")
        return snapshot

    async def list_stage_history(self, workflow_id: str) -> tuple[StageRun, ...]:
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            if await uow.workflows.get(workflow_id) is None:
                raise _not_found("workflow", "Workflow was not found")
            return await uow.workflows.list_stage_run_history(workflow_id)

    async def start_workflow(
        self,
        workflow_id: str,
        *,
        expected_version: int,
        correlation_id: str,
    ) -> WorkflowSnapshot:
        now = datetime.now(UTC)
        async with self._write_uow() as uow:
            workflow = await uow.workflows.start_workflow(
                workflow_id,
                expected_version=expected_version,
                updated_at=now,
            )
            await _append_event(
                uow,
                event_type="workflow.started",
                correlation_id=correlation_id,
                occurred_at=now,
                project_id=workflow.project_id,
                workflow_id=workflow.id,
                payload={"current_stage": workflow.current_stage.value},
            )
            await uow.commit()
            snapshot = await uow.workflows.get_snapshot(workflow_id)
        if snapshot is None:
            raise RuntimeError("workflow disappeared after start")
        return snapshot

    async def transition_stage(
        self,
        workflow_id: str,
        stage: Stage,
        target: StageRunState,
        *,
        expected_workflow_version: int,
        expected_stage_version: int,
        correlation_id: str,
    ) -> StageTransitionExecution:
        now = datetime.now(UTC)
        async with self._write_uow() as uow:
            workflow = await uow.workflows.get(workflow_id)
            run = await uow.workflows.get_current_stage_run(workflow_id, stage)
            if workflow is None:
                raise _not_found("workflow", "Workflow was not found")
            if run is None:
                raise _not_found("stage_run", "Stage run was not found")
            room = await uow.workflows.get_room_for_stage_run(run.id)
            if room is None:
                raise RuntimeError("stage run room is missing")
            active_agent_run = await uow.model_runtime.find_active_run_for_room(room.id)
            if active_agent_run is not None:
                raise DomainError(
                    code="stage_run.agent_run_active",
                    message="Stage cannot transition while an agent run is active",
                    category=ErrorCategory.CONFLICT,
                    details={"agent_run_id": active_agent_run.id},
                )
            require_stage_transition(run.state, target)
            updated_workflow, updated_run, unlocked = await uow.workflows.transition_stage(
                workflow_id,
                run.id,
                target,
                expected_workflow_version=expected_workflow_version,
                expected_stage_version=expected_stage_version,
                updated_at=now,
            )
            await _append_event(
                uow,
                event_type="stage_run.transitioned",
                correlation_id=correlation_id,
                occurred_at=now,
                project_id=updated_workflow.project_id,
                workflow_id=workflow_id,
                payload={
                    "stage_run_id": updated_run.id,
                    "stage": stage.value,
                    "previous_state": run.state.value,
                    "state": target.value,
                    "unlocked_stage": unlocked.stage.value if unlocked else None,
                },
            )
            await uow.commit()
        return StageTransitionExecution(
            workflow=updated_workflow,
            stage_run=updated_run,
            unlocked_stage_run=unlocked,
        )

    async def reopen_stage(
        self,
        workflow_id: str,
        stage: Stage,
        *,
        expected_workflow_version: int,
        correlation_id: str,
    ) -> WorkflowSnapshot:
        now = datetime.now(UTC)
        async with self._write_uow() as uow:
            snapshot = await uow.workflows.get_snapshot(workflow_id)
            if snapshot is None:
                raise _not_found("workflow", "Workflow was not found")
            by_stage = {run.stage: run for run in snapshot.stage_runs}
            for affected_run in snapshot.stage_runs[STAGE_ORDER.index(stage) :]:
                affected_room = await uow.workflows.get_room_for_stage_run(affected_run.id)
                if affected_room is None:
                    raise RuntimeError("stage run room is missing")
                active_agent_run = await uow.model_runtime.find_active_run_for_room(
                    affected_room.id
                )
                if active_agent_run is not None:
                    raise DomainError(
                        code="stage_run.agent_run_active",
                        message="Stage cannot reopen while an agent run is active",
                        category=ErrorCategory.CONFLICT,
                        details={"agent_run_id": active_agent_run.id},
                    )
            new_runs: list[StageRun] = []
            new_rooms: list[Room] = []
            for affected_stage in STAGE_ORDER[STAGE_ORDER.index(stage) :]:
                previous = by_stage[affected_stage]
                run = StageRun(
                    schema_version=1,
                    id=new_id("stagerun"),
                    workflow_id=workflow_id,
                    stage=affected_stage,
                    attempt=previous.attempt + 1,
                    state=(
                        StageRunState.READY if affected_stage is stage else StageRunState.LOCKED
                    ),
                    version=1,
                    created_at=now,
                )
                room = Room(
                    schema_version=1,
                    id=new_id("room"),
                    workflow_id=workflow_id,
                    stage_run_id=run.id,
                    stage=affected_stage,
                    status=RoomStatus.ACTIVE,
                    next_sequence=1,
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
                new_runs.append(run)
                new_rooms.append(room)
            reopened = await uow.workflows.reopen_stage(
                workflow_id,
                stage,
                tuple(new_runs),
                tuple(new_rooms),
                expected_workflow_version=expected_workflow_version,
                updated_at=now,
            )
            await _append_event(
                uow,
                event_type="stage_run.reopened",
                correlation_id=correlation_id,
                occurred_at=now,
                project_id=reopened.workflow.project_id,
                workflow_id=workflow_id,
                payload={"stage": stage.value, "attempt": new_runs[0].attempt},
            )
            await uow.commit()
        return reopened

    async def append_message(
        self,
        room_id: str,
        *,
        content: str,
        correction_of_id: str | None,
        expected_room_version: int,
        correlation_id: str,
    ) -> MessageAppendExecution:
        now = datetime.now(UTC)
        async with self._write_uow() as uow:
            room = await uow.workflows.get_room(room_id)
            if room is None:
                raise _not_found("room", "Room was not found")
            workflow = await uow.workflows.get(room.workflow_id)
            run = await uow.workflows.get_stage_run(room.stage_run_id)
            if workflow is None or run is None:
                raise RuntimeError("room workflow graph is incomplete")
            if room.status is RoomStatus.ACTIVE:
                current = await uow.workflows.get_current_stage_run(workflow.id, room.stage)
                if (
                    workflow.status is not WorkflowStatus.RUNNING
                    or current is None
                    or current.id != run.id
                    or run.state in {StageRunState.LOCKED, StageRunState.COMPLETED}
                ):
                    raise DomainError(
                        code="room.not_writable",
                        message="Room is not writable in the current workflow state",
                        category=ErrorCategory.CONFLICT,
                    )
            kind = (
                MessageKind.CORRECTION
                if correction_of_id is not None
                else (
                    MessageKind.CONSULTATION
                    if room.status is RoomStatus.CONSULTATION
                    else MessageKind.DISCUSSION
                )
            )
            message = Message(
                schema_version=1,
                id=new_id("message"),
                room_id=room_id,
                sequence=room.next_sequence,
                author=MessageAuthor.USER,
                kind=kind,
                content=content.strip(),
                correction_of_id=correction_of_id,
                created_at=now,
            )
            updated_room = await uow.workflows.append_message(
                message,
                expected_room_version=expected_room_version,
                updated_at=now,
            )
            await _append_event(
                uow,
                event_type="message.appended",
                correlation_id=correlation_id,
                occurred_at=now,
                project_id=workflow.project_id,
                workflow_id=workflow.id,
                room_id=room_id,
                payload={
                    "message_id": message.id,
                    "sequence": message.sequence,
                    "kind": message.kind.value,
                },
            )
            await uow.commit()
        return MessageAppendExecution(message=message, room=updated_room)

    async def list_messages(
        self,
        room_id: str,
        *,
        after_sequence: int,
        limit: int,
    ) -> tuple[Message, ...]:
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            return await uow.workflows.list_messages(
                room_id,
                after_sequence=after_sequence,
                limit=limit,
            )

    async def enqueue_task(
        self,
        room_id: str,
        *,
        title: str,
        payload: dict[str, object],
        correlation_id: str,
    ) -> WorkflowTask:
        now = datetime.now(UTC)
        async with self._write_uow() as uow:
            room = await uow.workflows.get_room(room_id)
            if room is None:
                raise _not_found("room", "Room was not found")
            workflow = await uow.workflows.get(room.workflow_id)
            run = await uow.workflows.get_stage_run(room.stage_run_id)
            current = await uow.workflows.get_current_stage_run(room.workflow_id, room.stage)
            if workflow is None or run is None:
                raise RuntimeError("room workflow graph is incomplete")
            if (
                workflow.status is not WorkflowStatus.RUNNING
                or room.status is not RoomStatus.ACTIVE
                or current is None
                or current.id != run.id
                or run.state
                in {
                    StageRunState.LOCKED,
                    StageRunState.COMPLETED,
                    StageRunState.FAILED,
                    StageRunState.CANCELLED,
                    StageRunState.ABANDONED,
                }
            ):
                raise DomainError(
                    code="task.room_not_active",
                    message="Tasks require the active current stage room",
                    category=ErrorCategory.CONFLICT,
                )
            task = WorkflowTask(
                schema_version=1,
                id=new_id("task"),
                workflow_id=workflow.id,
                stage_run_id=run.id,
                room_id=room.id,
                title=title.strip(),
                status=TaskStatus.QUEUED,
                payload=payload,
                version=1,
                created_at=now,
            )
            await uow.workflows.add_task(task)
            await _append_event(
                uow,
                event_type="task.queued",
                correlation_id=correlation_id,
                occurred_at=now,
                project_id=workflow.project_id,
                workflow_id=workflow.id,
                room_id=room.id,
                task_id=task.id,
                payload={"title": task.title},
            )
            await uow.commit()
        return task

    async def list_tasks(
        self,
        workflow_id: str,
        *,
        status: TaskStatus | None,
    ) -> tuple[WorkflowTask, ...]:
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            if await uow.workflows.get(workflow_id) is None:
                raise _not_found("workflow", "Workflow was not found")
            return await uow.workflows.list_tasks(workflow_id, status=status)

    async def start_task(
        self,
        task_id: str,
        *,
        expected_version: int,
        correlation_id: str,
    ) -> WorkflowTask:
        return await self._mutate_task(
            task_id,
            event_type="task.started",
            correlation_id=correlation_id,
            mutate=lambda uow, now: uow.workflows.start_task(
                task_id,
                expected_version=expected_version,
                started_at=now,
            ),
        )

    async def complete_task(
        self,
        task_id: str,
        *,
        succeeded: bool,
        result: dict[str, object],
        expected_version: int,
        correlation_id: str,
    ) -> WorkflowTask:
        return await self._mutate_task(
            task_id,
            event_type="task.completed",
            correlation_id=correlation_id,
            mutate=lambda uow, now: uow.workflows.complete_task(
                task_id,
                succeeded=succeeded,
                result=result,
                expected_version=expected_version,
                completed_at=now,
            ),
        )

    async def cancel_task(
        self,
        task_id: str,
        *,
        expected_version: int,
        correlation_id: str,
    ) -> WorkflowTask:
        return await self._mutate_task(
            task_id,
            event_type="task.cancelled",
            correlation_id=correlation_id,
            mutate=lambda uow, now: uow.workflows.cancel_task(
                task_id,
                expected_version=expected_version,
                completed_at=now,
            ),
        )

    async def _mutate_task(
        self,
        task_id: str,
        *,
        event_type: str,
        correlation_id: str,
        mutate: TaskMutation,
    ) -> WorkflowTask:
        now = datetime.now(UTC)
        async with self._write_uow() as uow:
            task = await mutate(uow, now)
            workflow = await uow.workflows.get(task.workflow_id)
            if workflow is None:
                raise RuntimeError("task workflow is missing")
            await _append_event(
                uow,
                event_type=event_type,
                correlation_id=correlation_id,
                occurred_at=now,
                project_id=workflow.project_id,
                workflow_id=workflow.id,
                room_id=task.room_id,
                task_id=task.id,
                payload={"status": task.status.value},
            )
            await uow.commit()
        return task

    def _write_uow(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(
            self._database.sessions,
            delivery_targets=(LOCAL_AUDIT_CONSUMER, WEBSOCKET_CONSUMER),
            write=True,
            write_lock=self._database.write_lock,
        )


async def _append_event(
    uow: SqlAlchemyUnitOfWork,
    *,
    event_type: str,
    correlation_id: str,
    occurred_at: datetime,
    project_id: str,
    workflow_id: str,
    payload: dict[str, object],
    room_id: str | None = None,
    task_id: str | None = None,
) -> int:
    return await uow.events.append(
        envelope=EventEnvelope(
            schema_version=1,
            event_type=event_type,
            correlation_id=correlation_id,
            actor=ActorRef(type=ActorType.USER, id="user_local"),
            source=EventSource.BACKEND,
            occurred_at=occurred_at,
            project_id=project_id,
            workflow_id=workflow_id,
            room_id=room_id,
            task_id=task_id,
            payload=payload,
        ),
        aggregate_type="workflow",
        aggregate_id=workflow_id,
    )


def _not_found(code: str, message: str) -> DomainError:
    return DomainError(
        code=f"{code}.not_found",
        message=message,
        category=ErrorCategory.NOT_FOUND,
    )
