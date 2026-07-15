from __future__ import annotations

from typing import Annotated, Any, cast

from fastapi import APIRouter, Query, Request
from fastapi import Path as ApiPath
from pydantic import BaseModel, ConfigDict, Field

from agent_platform.application.workflows import WorkflowApplicationService
from agent_platform.domain.contracts import Stage, StageRunState
from agent_platform.domain.workflows import (
    Message,
    Room,
    StageRun,
    TaskStatus,
    Workflow,
    WorkflowSnapshot,
    WorkflowTask,
)

router = APIRouter(tags=["workflows"])
CorrelationId = Annotated[str, Field(min_length=1, max_length=120)]
ProjectIdPath = Annotated[str, ApiPath(pattern=r"^project_[a-z0-9]+$")]
WorkflowIdPath = Annotated[str, ApiPath(pattern=r"^workflow_[a-z0-9]+$")]
RoomIdPath = Annotated[str, ApiPath(pattern=r"^room_[a-z0-9]+$")]
TaskIdPath = Annotated[str, ApiPath(pattern=r"^task_[a-z0-9]+$")]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class WorkflowCreateRequest(ApiModel):
    title: str = Field(min_length=1, max_length=200)
    correlation_id: CorrelationId


class WorkflowListResponse(ApiModel):
    workflows: tuple[Workflow, ...]


class WorkflowVersionRequest(ApiModel):
    expected_version: int = Field(gt=0)
    correlation_id: CorrelationId


class StageTransitionRequest(ApiModel):
    target_state: StageRunState
    expected_workflow_version: int = Field(gt=0)
    expected_stage_version: int = Field(gt=0)
    correlation_id: CorrelationId


class StageTransitionResponse(ApiModel):
    workflow: Workflow
    stage_run: StageRun
    unlocked_stage_run: StageRun | None


class StageRunHistoryResponse(ApiModel):
    stage_runs: tuple[StageRun, ...]


class MessageAppendRequest(ApiModel):
    content: str = Field(min_length=1, max_length=100_000)
    correction_of_id: str | None = Field(
        default=None,
        pattern=r"^message_[a-z0-9]+$",
    )
    expected_room_version: int = Field(gt=0)
    correlation_id: CorrelationId


class MessageAppendResponse(ApiModel):
    message: Message
    room: Room


class MessageListResponse(ApiModel):
    messages: tuple[Message, ...]


class TaskCreateRequest(ApiModel):
    title: str = Field(min_length=1, max_length=200)
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: CorrelationId


class TaskListResponse(ApiModel):
    tasks: tuple[WorkflowTask, ...]


class TaskVersionRequest(ApiModel):
    expected_version: int = Field(gt=0)
    correlation_id: CorrelationId


class TaskCompleteRequest(TaskVersionRequest):
    succeeded: bool
    result: dict[str, Any] = Field(default_factory=dict)


@router.post(
    "/projects/{project_id}/workflows",
    response_model=WorkflowSnapshot,
    status_code=201,
)
async def create_workflow(
    project_id: ProjectIdPath,
    payload: WorkflowCreateRequest,
    request: Request,
) -> WorkflowSnapshot:
    return await _service(request).create_workflow(
        project_id,
        title=payload.title,
        correlation_id=payload.correlation_id,
    )


@router.get("/projects/{project_id}/workflows", response_model=WorkflowListResponse)
async def list_workflows(
    project_id: ProjectIdPath,
    request: Request,
) -> WorkflowListResponse:
    workflows = await _service(request).list_workflows(project_id)
    return WorkflowListResponse(workflows=workflows)


@router.get("/workflows/{workflow_id}", response_model=WorkflowSnapshot)
async def get_workflow(
    workflow_id: WorkflowIdPath,
    request: Request,
) -> WorkflowSnapshot:
    return await _service(request).get_workflow(workflow_id)


@router.post("/workflows/{workflow_id}/start", response_model=WorkflowSnapshot)
async def start_workflow(
    workflow_id: WorkflowIdPath,
    payload: WorkflowVersionRequest,
    request: Request,
) -> WorkflowSnapshot:
    return await _service(request).start_workflow(
        workflow_id,
        expected_version=payload.expected_version,
        correlation_id=payload.correlation_id,
    )


@router.get(
    "/workflows/{workflow_id}/stage-runs/history",
    response_model=StageRunHistoryResponse,
)
async def list_stage_history(
    workflow_id: WorkflowIdPath,
    request: Request,
) -> StageRunHistoryResponse:
    stage_runs = await _service(request).list_stage_history(workflow_id)
    return StageRunHistoryResponse(stage_runs=stage_runs)


@router.post(
    "/workflows/{workflow_id}/stages/{stage}/transition",
    response_model=StageTransitionResponse,
)
async def transition_stage(
    workflow_id: WorkflowIdPath,
    stage: Stage,
    payload: StageTransitionRequest,
    request: Request,
) -> StageTransitionResponse:
    execution = await _service(request).transition_stage(
        workflow_id,
        stage,
        payload.target_state,
        expected_workflow_version=payload.expected_workflow_version,
        expected_stage_version=payload.expected_stage_version,
        correlation_id=payload.correlation_id,
    )
    return StageTransitionResponse(
        workflow=execution.workflow,
        stage_run=execution.stage_run,
        unlocked_stage_run=execution.unlocked_stage_run,
    )


@router.post(
    "/workflows/{workflow_id}/stages/{stage}/reopen",
    response_model=WorkflowSnapshot,
)
async def reopen_stage(
    workflow_id: WorkflowIdPath,
    stage: Stage,
    payload: WorkflowVersionRequest,
    request: Request,
) -> WorkflowSnapshot:
    return await _service(request).reopen_stage(
        workflow_id,
        stage,
        expected_workflow_version=payload.expected_version,
        correlation_id=payload.correlation_id,
    )


@router.post("/rooms/{room_id}/messages", response_model=MessageAppendResponse, status_code=201)
async def append_message(
    room_id: RoomIdPath,
    payload: MessageAppendRequest,
    request: Request,
) -> MessageAppendResponse:
    execution = await _service(request).append_message(
        room_id,
        content=payload.content,
        correction_of_id=payload.correction_of_id,
        expected_room_version=payload.expected_room_version,
        correlation_id=payload.correlation_id,
    )
    return MessageAppendResponse(message=execution.message, room=execution.room)


@router.get("/rooms/{room_id}/messages", response_model=MessageListResponse)
async def list_messages(
    room_id: RoomIdPath,
    request: Request,
    after_sequence: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> MessageListResponse:
    messages = await _service(request).list_messages(
        room_id,
        after_sequence=after_sequence,
        limit=limit,
    )
    return MessageListResponse(messages=messages)


@router.post("/rooms/{room_id}/tasks", response_model=WorkflowTask, status_code=201)
async def enqueue_task(
    room_id: RoomIdPath,
    payload: TaskCreateRequest,
    request: Request,
) -> WorkflowTask:
    return await _service(request).enqueue_task(
        room_id,
        title=payload.title,
        payload=payload.payload,
        correlation_id=payload.correlation_id,
    )


@router.get("/workflows/{workflow_id}/tasks", response_model=TaskListResponse)
async def list_tasks(
    workflow_id: WorkflowIdPath,
    request: Request,
    status: Annotated[TaskStatus | None, Query()] = None,
) -> TaskListResponse:
    tasks = await _service(request).list_tasks(workflow_id, status=status)
    return TaskListResponse(tasks=tasks)


@router.post("/tasks/{task_id}/start", response_model=WorkflowTask)
async def start_task(
    task_id: TaskIdPath,
    payload: TaskVersionRequest,
    request: Request,
) -> WorkflowTask:
    return await _service(request).start_task(
        task_id,
        expected_version=payload.expected_version,
        correlation_id=payload.correlation_id,
    )


@router.post("/tasks/{task_id}/complete", response_model=WorkflowTask)
async def complete_task(
    task_id: TaskIdPath,
    payload: TaskCompleteRequest,
    request: Request,
) -> WorkflowTask:
    return await _service(request).complete_task(
        task_id,
        succeeded=payload.succeeded,
        result=payload.result,
        expected_version=payload.expected_version,
        correlation_id=payload.correlation_id,
    )


@router.post("/tasks/{task_id}/cancel", response_model=WorkflowTask)
async def cancel_task(
    task_id: TaskIdPath,
    payload: TaskVersionRequest,
    request: Request,
) -> WorkflowTask:
    return await _service(request).cancel_task(
        task_id,
        expected_version=payload.expected_version,
        correlation_id=payload.correlation_id,
    )


def _service(request: Request) -> WorkflowApplicationService:
    return cast(WorkflowApplicationService, request.app.state.workflow_service)
