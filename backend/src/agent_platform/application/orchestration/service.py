from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from agent_platform.application.governance import GovernanceApplicationService
from agent_platform.application.model_runtime import AgentRuntimeService
from agent_platform.application.orchestration.context import build_project_context
from agent_platform.application.tooling import ToolApplicationService
from agent_platform.application.workflows import (
    StageTransitionExecution,
    WorkflowApplicationService,
)
from agent_platform.config.settings import Settings
from agent_platform.domain.contracts import (
    CapabilityAccess,
    Stage,
    StageRunState,
    get_stage_contract,
)
from agent_platform.domain.governance import GateResolution, ToolCallStatus
from agent_platform.domain.model_runtime import AgentRunStatus
from agent_platform.domain.orchestration import (
    OrchestrationFrame,
    OrchestrationFrameType,
    PlannedToolAction,
    StageExecutionPlan,
)
from agent_platform.domain.projects import PersistedProjectManifest, ProjectRegistration
from agent_platform.domain.shared.errors import DomainError, ErrorCategory
from agent_platform.domain.tooling import ToolOperation
from agent_platform.domain.workflows import (
    Room,
    StageRun,
    TaskStatus,
    WorkflowSnapshot,
    WorkflowStatus,
    WorkflowTask,
)
from agent_platform.infrastructure.database import Database
from agent_platform.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from agent_platform.infrastructure.projects.paths import resolve_project_path
from agent_platform.infrastructure.tooling import AtomicFileTools, ToolCatalog

_ARTIFACT_TOOLS = {
    Stage.PLANNER: "filesystem.write_planner_artifact",
    Stage.DESIGNER: "filesystem.write_designer_artifact",
    Stage.BUILDER: "filesystem.write_builder_artifact",
    Stage.REVIEWER: "filesystem.write_reviewer_artifact",
    Stage.DEPLOYER: "filesystem.write_deployment_document",
}
_ARTIFACT_TOOL_NAMES = frozenset(_ARTIFACT_TOOLS.values())
_STAGE_LABELS = {
    Stage.PLANNER: "Planner",
    Stage.DESIGNER: "Designer",
    Stage.BUILDER: "Builder",
    Stage.REVIEWER: "Reviewer",
    Stage.DEPLOYER: "Deployer",
}


class OrchestrationApplicationService:
    def __init__(
        self,
        database: Database,
        settings: Settings,
        workflows: WorkflowApplicationService,
        runtime: AgentRuntimeService,
        tooling: ToolApplicationService,
        governance: GovernanceApplicationService,
        catalog: ToolCatalog,
        file_tools: AtomicFileTools,
    ) -> None:
        self._database = database
        self._settings = settings
        self._workflows = workflows
        self._runtime = runtime
        self._tooling = tooling
        self._governance = governance
        self._catalog = catalog
        self._file_tools = file_tools

    async def stream_stage(
        self,
        workflow_id: str,
        *,
        request_key: str,
        instruction: str,
        correlation_id: str,
    ) -> AsyncIterator[OrchestrationFrame]:
        sequence = 0
        task: WorkflowTask | None = None
        stage_run: StageRun | None = None
        room: Room | None = None
        agent_run_id: str | None = None

        def frame(
            frame_type: OrchestrationFrameType,
            *,
            text: str | None = None,
            error_code: str | None = None,
            data: dict[str, Any] | None = None,
        ) -> OrchestrationFrame:
            nonlocal sequence
            if stage_run is None:
                raise RuntimeError("orchestration stage context is unavailable")
            sequence += 1
            return OrchestrationFrame(
                type=frame_type,
                workflow_id=workflow_id,
                stage_run_id=stage_run.id,
                sequence=sequence,
                agent_run_id=agent_run_id,
                task_id=task.id if task is not None else None,
                text=text,
                error_code=error_code,
                data=data or {},
            )

        try:
            snapshot = await self._workflows.get_workflow(workflow_id)
            stage_run, room = _current_stage_context(snapshot)
            yield frame(
                OrchestrationFrameType.STARTED,
                data={"stage": stage_run.stage.value, "request_key": request_key},
            )
            _require_orchestratable(snapshot, stage_run)

            for target in _required_production_transitions(stage_run.state):
                transition = await self._transition(
                    workflow_id,
                    stage_run.stage,
                    target,
                    correlation_id=f"{correlation_id}:{target.value}",
                )
                stage_run = transition.stage_run
                yield frame(
                    OrchestrationFrameType.STAGE_TRANSITIONED,
                    data={"state": stage_run.state.value},
                )

            tasks = await self._workflows.list_tasks(workflow_id, status=None)
            task = _task_for_request(tasks, stage_run.id, request_key)
            if (
                stage_run.state in {StageRunState.P2R_REVIEWING, StageRunState.QUALITY_CHECKING}
                and task is None
            ):
                raise _conflict(
                    "orchestration.resume_key_required",
                    "Incomplete gate processing must resume with its original request key",
                )
            if task is None:
                task = await self._workflows.enqueue_task(
                    room.id,
                    title=f"{_STAGE_LABELS[stage_run.stage]} formal delivery",
                    payload={
                        "orchestration_request_key": request_key,
                        "instruction": instruction,
                    },
                    correlation_id=f"{correlation_id}:task:create",
                )
            if task.status is TaskStatus.QUEUED:
                task = await self._workflows.start_task(
                    task.id,
                    expected_version=task.version,
                    correlation_id=f"{correlation_id}:task:start",
                )
            if task.status not in {TaskStatus.RUNNING, TaskStatus.SUCCEEDED}:
                raise _conflict(
                    "orchestration.request_terminal",
                    "Orchestration request already ended without a resumable task",
                )
            yield frame(
                OrchestrationFrameType.TASK_STARTED,
                data={"status": task.status.value},
            )

            registration, persisted_manifest = await self._project_context(
                snapshot.workflow.project_id
            )
            context = await asyncio.to_thread(
                build_project_context,
                registration,
                persisted_manifest,
                max_characters=max(
                    10_000,
                    min(self._settings.model_context_max_characters // 2, 150_000),
                ),
            )
            creation = await self._runtime.create_run(
                room.id,
                request_key=request_key,
                formal=True,
                correlation_id=f"{correlation_id}:agent:create",
            )
            agent_run_id = creation.run.id
            yield frame(
                OrchestrationFrameType.AGENT_RUN_CREATED,
                data={"created": creation.created, "status": creation.run.status.value},
            )
            if creation.run.status is AgentRunStatus.PENDING:
                async for agent_frame in self._runtime.stream_run(
                    agent_run_id,
                    instruction=instruction,
                    correlation_id=f"{correlation_id}:agent:stream",
                    execution_contract=_execution_contract(stage_run.stage, self._catalog),
                    project_file_content=context.text,
                ):
                    yield frame(
                        OrchestrationFrameType.AGENT_FRAME,
                        data={"agent_frame": agent_frame.model_dump(mode="json")},
                    )
            agent_snapshot = await self._runtime.get_run(agent_run_id)
            if agent_snapshot.run.status is not AgentRunStatus.SUCCEEDED:
                raise _conflict(
                    "orchestration.agent_run_failed",
                    "Formal agent run did not produce an executable plan",
                )
            plan = _parse_plan(await self._runtime.get_output(agent_run_id))
            _validate_plan(stage_run.stage, plan, self._catalog)
            yield frame(
                OrchestrationFrameType.PLAN_VALIDATED,
                text=plan.summary,
                data={"action_count": len(plan.actions)},
            )

            if task.status is TaskStatus.RUNNING:
                seen_paths: set[str] = set()
                tool_call_ids: list[str] = []
                for index, action in enumerate(plan.actions):
                    _validate_action_path(
                        action,
                        Path(registration.workspace.root_path),
                        self._file_tools,
                        seen_paths,
                    )
                    execution = await self._tooling.execute(
                        task.id,
                        tool_name=action.tool_name,
                        idempotency_key=_derived_key(request_key, f"action-{index}"),
                        arguments=action.arguments,
                        timeout_seconds=action.timeout_seconds,
                        correlation_id=f"{correlation_id}:tool:{index}",
                    )
                    tool_call_ids.append(execution.call.id)
                    yield frame(
                        OrchestrationFrameType.TOOL_COMPLETED,
                        data=execution.call.model_dump(mode="json"),
                    )
                    if execution.call.status is not ToolCallStatus.SUCCEEDED:
                        raise _conflict(
                            execution.call.error_code or "orchestration.tool_failed",
                            "A planned tool action did not succeed",
                        )

                artifact_path = _artifact_path(stage_run.stage)
                artifact_arguments = {
                    "path": artifact_path,
                    "content": plan.artifact_content,
                    "expected_hash": _current_hash(
                        self._file_tools,
                        Path(registration.workspace.root_path),
                        artifact_path,
                    ),
                }
                artifact_write = await self._tooling.execute(
                    task.id,
                    tool_name=_ARTIFACT_TOOLS[stage_run.stage],
                    idempotency_key=_derived_key(request_key, "stage-artifact"),
                    arguments=artifact_arguments,
                    timeout_seconds=30,
                    correlation_id=f"{correlation_id}:tool:artifact",
                )
                tool_call_ids.append(artifact_write.call.id)
                yield frame(
                    OrchestrationFrameType.TOOL_COMPLETED,
                    data=artifact_write.call.model_dump(mode="json"),
                )
                if artifact_write.call.status is not ToolCallStatus.SUCCEEDED:
                    raise _conflict(
                        artifact_write.call.error_code or "orchestration.artifact_write_failed",
                        "The stage artifact could not be written",
                    )
                task = await self._workflows.complete_task(
                    task.id,
                    succeeded=True,
                    result={
                        "agent_run_id": agent_run_id,
                        "artifact_path": artifact_path,
                        "summary": plan.summary,
                        "tool_call_ids": tool_call_ids,
                    },
                    expected_version=task.version,
                    correlation_id=f"{correlation_id}:task:complete",
                )
            yield frame(
                OrchestrationFrameType.TASK_COMPLETED,
                data={"status": task.status.value},
            )

            artifact, version = await self._governance.create_artifact_version(
                stage_run.id,
                name=f"{_STAGE_LABELS[stage_run.stage]} deliverable",
                relative_path=_artifact_path(stage_run.stage),
                correlation_id=f"{correlation_id}:artifact:version",
            )
            yield frame(
                OrchestrationFrameType.ARTIFACT_CREATED,
                data={
                    "artifact": artifact.model_dump(mode="json"),
                    "version": version.model_dump(mode="json"),
                },
            )
            snapshot = await self._workflows.get_workflow(workflow_id)
            stage_run, room = _current_stage_context(snapshot)
            for target in _required_gate_transitions(stage_run.state):
                transition = await self._transition(
                    workflow_id,
                    stage_run.stage,
                    target,
                    correlation_id=f"{correlation_id}:{target.value}",
                )
                stage_run = transition.stage_run
                yield frame(
                    OrchestrationFrameType.STAGE_TRANSITIONED,
                    data={"state": stage_run.state.value},
                )
            gate = await self._governance.evaluate_gate(
                stage_run.id,
                artifact_version_ids=(version.id,),
                correlation_id=f"{correlation_id}:gate",
            )
            yield frame(
                OrchestrationFrameType.GATE_EVALUATED,
                data=gate.gate.model_dump(mode="json"),
            )
            if gate.approval is not None:
                yield frame(
                    OrchestrationFrameType.APPROVAL_REQUIRED,
                    data=gate.approval.model_dump(mode="json"),
                )
            if gate.handoff is not None:
                yield frame(
                    OrchestrationFrameType.HANDOFF_CREATED,
                    data=gate.handoff.model_dump(mode="json"),
                )
            yield frame(
                OrchestrationFrameType.COMPLETED,
                data={
                    "gate_resolution": gate.gate.resolution.value,
                    "next_action": (
                        "approval"
                        if gate.gate.resolution is GateResolution.PENDING
                        else "rewrite"
                        if gate.gate.resolution is GateResolution.REWRITE_REQUIRED
                        else "next_stage"
                    ),
                },
            )
        except asyncio.CancelledError:
            if task is not None and task.status is TaskStatus.RUNNING:
                await self._workflows.cancel_task(
                    task.id,
                    expected_version=task.version,
                    correlation_id=f"{correlation_id}:task:cancel",
                )
            raise
        except DomainError as error:
            if task is not None and task.status is TaskStatus.RUNNING:
                task = await self._fail_task(task, error.code, correlation_id)
            if stage_run is None:
                raise
            yield frame(
                OrchestrationFrameType.ERROR,
                text=error.message,
                error_code=error.code,
                data={"category": error.category.value, "retryable": error.retryable},
            )
        except Exception:
            if task is not None and task.status is TaskStatus.RUNNING:
                task = await self._fail_task(
                    task,
                    "orchestration.internal_failure",
                    correlation_id,
                )
            if stage_run is None:
                raise
            yield frame(
                OrchestrationFrameType.ERROR,
                text="The orchestration run failed unexpectedly",
                error_code="orchestration.internal_failure",
            )

    async def _transition(
        self,
        workflow_id: str,
        stage: Stage,
        target: StageRunState,
        *,
        correlation_id: str,
    ) -> StageTransitionExecution:
        snapshot = await self._workflows.get_workflow(workflow_id)
        run, _ = _current_stage_context(snapshot)
        return await self._workflows.transition_stage(
            workflow_id,
            stage,
            target,
            expected_workflow_version=snapshot.workflow.version,
            expected_stage_version=run.version,
            correlation_id=correlation_id,
        )

    async def _project_context(
        self, project_id: str
    ) -> tuple[ProjectRegistration, PersistedProjectManifest]:
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            registration = await uow.projects.get(project_id)
            manifest = await uow.projects.get_manifest(project_id)
        if registration is None or manifest is None:
            raise RuntimeError("orchestration project context is incomplete")
        return registration, manifest

    async def _fail_task(
        self,
        task: WorkflowTask,
        error_code: str,
        correlation_id: str,
    ) -> WorkflowTask:
        try:
            return await self._workflows.complete_task(
                task.id,
                succeeded=False,
                result={"error_code": error_code},
                expected_version=task.version,
                correlation_id=f"{correlation_id}:task:failed",
            )
        except DomainError:
            return task


def _current_stage_context(snapshot: WorkflowSnapshot) -> tuple[StageRun, Room]:
    candidates = [
        run for run in snapshot.stage_runs if run.stage is snapshot.workflow.current_stage
    ]
    if not candidates:
        raise RuntimeError("workflow current stage run is missing")
    run = max(candidates, key=lambda candidate: candidate.attempt)
    room = next(
        (candidate for candidate in snapshot.rooms if candidate.stage_run_id == run.id), None
    )
    if room is None:
        raise RuntimeError("workflow current stage room is missing")
    return run, room


def _require_orchestratable(snapshot: WorkflowSnapshot, run: StageRun) -> None:
    if snapshot.workflow.status is not WorkflowStatus.RUNNING:
        raise _conflict(
            "orchestration.workflow_not_running",
            "Formal orchestration requires a running workflow",
        )
    if run.state not in {
        StageRunState.READY,
        StageRunState.DISCUSSING,
        StageRunState.PRODUCING,
        StageRunState.P2R_REVIEWING,
        StageRunState.QUALITY_CHECKING,
        StageRunState.NEEDS_FIX,
    }:
        raise _conflict(
            "orchestration.stage_not_runnable",
            "Current stage is not ready for formal orchestration",
        )


def _required_production_transitions(state: StageRunState) -> tuple[StageRunState, ...]:
    if state is StageRunState.READY:
        return (StageRunState.DISCUSSING, StageRunState.PRODUCING)
    if state is StageRunState.DISCUSSING:
        return (StageRunState.PRODUCING,)
    if state is StageRunState.NEEDS_FIX:
        return (StageRunState.PRODUCING,)
    return ()


def _required_gate_transitions(state: StageRunState) -> tuple[StageRunState, ...]:
    if state is StageRunState.PRODUCING:
        return (StageRunState.P2R_REVIEWING, StageRunState.QUALITY_CHECKING)
    if state is StageRunState.P2R_REVIEWING:
        return (StageRunState.QUALITY_CHECKING,)
    if state is StageRunState.QUALITY_CHECKING:
        return ()
    raise _conflict(
        "orchestration.stage_not_gate_ready",
        "Current stage cannot enter quality checking",
    )


def _task_for_request(
    tasks: tuple[WorkflowTask, ...],
    stage_run_id: str,
    request_key: str,
) -> WorkflowTask | None:
    matches = [
        task
        for task in tasks
        if task.stage_run_id == stage_run_id
        and task.payload.get("orchestration_request_key") == request_key
    ]
    if len(matches) > 1:
        raise RuntimeError("orchestration request has duplicate tasks")
    return matches[0] if matches else None


def _parse_plan(output: str) -> StageExecutionPlan:
    candidate = output.strip()
    if candidate.startswith("```"):
        first_newline = candidate.find("\n")
        last_fence = candidate.rfind("```")
        if first_newline != -1 and last_fence > first_newline:
            candidate = candidate[first_newline + 1 : last_fence].strip()
    if not candidate.startswith("{"):
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end > start:
            candidate = candidate[start : end + 1]
    try:
        return StageExecutionPlan.model_validate_json(candidate)
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
        raise _invalid(
            "orchestration.plan_invalid",
            "Formal model output does not satisfy StageExecutionPlan v1",
        ) from None


def _validate_plan(stage: Stage, plan: StageExecutionPlan, catalog: ToolCatalog) -> None:
    contract = get_stage_contract(stage)
    for action in plan.actions:
        if action.tool_name in _ARTIFACT_TOOL_NAMES:
            raise _invalid(
                "orchestration.plan_artifact_action_forbidden",
                "Stage artifact is written only by the orchestrator",
            )
        tool = catalog.get(action.tool_name)
        if tool.operation is ToolOperation.READ:
            raise _invalid(
                "orchestration.plan_read_action_invalid",
                "Execution plan cannot read files after model reconciliation",
            )
        access = contract.capability_access(tool.capability)
        if access is not CapabilityAccess.DEFAULT:
            raise DomainError(
                code=(
                    "orchestration.capability_approval_required"
                    if access is CapabilityAccess.REQUIRES_APPROVAL
                    else "orchestration.capability_forbidden"
                ),
                message="Planned tool action is not a default stage capability",
                category=ErrorCategory.PERMISSION,
                details={"tool_name": action.tool_name},
            )


def _validate_action_path(
    action: PlannedToolAction,
    workspace_root: Path,
    file_tools: AtomicFileTools,
    seen_paths: set[str],
) -> None:
    if not action.tool_name.startswith("filesystem."):
        return
    path_value = action.arguments.get("path")
    if not isinstance(path_value, str):
        raise _invalid("orchestration.plan_path_invalid", "Filesystem action requires a path")
    if path_value in seen_paths:
        raise _invalid(
            "orchestration.plan_duplicate_path",
            "Execution plan contains repeated filesystem actions for one path",
        )
    seen_paths.add(path_value)
    if action.tool_name.startswith("filesystem.write_"):
        supplied_hash = action.arguments.get("expected_hash")
        current_hash = _current_hash(file_tools, workspace_root, path_value)
        if supplied_hash != current_hash:
            raise _conflict(
                "orchestration.plan_hash_conflict",
                "Planned file version does not match the current workspace",
            )


def _current_hash(
    file_tools: AtomicFileTools,
    workspace_root: Path,
    relative_path: str,
) -> str | None:
    target = resolve_project_path(workspace_root, relative_path, must_exist=False)
    if not target.exists() and not target.is_symlink():
        return None
    result, _ = file_tools.read(workspace_root, relative_path)
    return result.content_hash


def _execution_contract(stage: Stage, catalog: ToolCatalog) -> str:
    contract = get_stage_contract(stage)
    allowed_tools = []
    for tool in catalog.list():
        if tool.name in _ARTIFACT_TOOL_NAMES:
            continue
        if tool.operation is ToolOperation.READ:
            continue
        if contract.capability_access(tool.capability) is not CapabilityAccess.DEFAULT:
            continue
        allowed_tools.append(
            {
                "name": tool.name,
                "operation": tool.operation.value,
                "arguments": _tool_argument_contract(tool.operation),
                "max_timeout_seconds": tool.max_timeout_seconds,
            }
        )
    schema = {
        "schema_version": 1,
        "summary": "non-empty string",
        "artifact_content": "complete final UTF-8 stage deliverable",
        "actions": [
            {
                "tool_name": "one allowed tool name",
                "arguments": {
                    "path": "canonical/project/path for filesystem tools",
                    "content": "complete file content for write tools",
                    "expected_hash": "workspace sha256 when overwriting, otherwise null",
                    "command_index": "ProjectManifest index for command tools",
                },
                "timeout_seconds": "positive integer within catalog limit",
            }
        ],
    }
    return (
        "AGENTPROGRAM_STAGE_EXECUTION_PLAN_V1\n"
        "The P0 draft and final P2R response must be exactly one JSON object with no Markdown "
        "fence or surrounding prose. Reviewer responses remain plain review text. The final JSON "
        "must satisfy this shape:\n"
        f"{json.dumps(schema, ensure_ascii=False, indent=2)}\n"
        f"Current stage: {stage.value}. Allowed planned tools:\n"
        f"{json.dumps(allowed_tools, ensure_ascii=False, indent=2)}\n"
        "Do not include the stage artifact write in actions; put that complete document in "
        "artifact_content. Use only current hashes shown in project file context. Commands must "
        "use command_index and never contain an argv or shell string. If no project mutation is "
        "needed, return an empty actions array."
    )


def _artifact_path(stage: Stage) -> str:
    return f"artifacts/{stage.value}/{stage.value}-deliverable.md"


def _tool_argument_contract(operation: ToolOperation) -> dict[str, str]:
    if operation is ToolOperation.COMMAND:
        return {"command_index": "zero-based ProjectManifest command index"}
    if operation is ToolOperation.WRITE:
        return {
            "path": "canonical project-relative path",
            "content": "complete UTF-8 file content",
            "expected_hash": "current SHA-256 or null for a new file",
        }
    if operation is ToolOperation.DELETE:
        return {
            "path": "canonical project-relative path",
            "expected_hash": "current SHA-256",
        }
    return {"path": "canonical project-relative path"}


def _derived_key(request_key: str, suffix: str) -> str:
    available = 128 - len(suffix) - 1
    return f"{request_key[:available]}:{suffix}"


def _invalid(code: str, message: str) -> DomainError:
    return DomainError(code=code, message=message, category=ErrorCategory.INVALID_INPUT)


def _conflict(code: str, message: str) -> DomainError:
    return DomainError(code=code, message=message, category=ErrorCategory.CONFLICT)
