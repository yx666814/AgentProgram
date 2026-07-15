from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_platform.config.settings import Settings
from agent_platform.domain.contracts import (
    CapabilityAccess,
    CapabilityRisk,
    StageRunState,
    get_stage_contract,
)
from agent_platform.domain.events import ActorRef, ActorType, EventEnvelope, EventSource
from agent_platform.domain.governance import (
    Approval,
    ApprovalKind,
    ApprovalStatus,
    CapabilityRequestRecord,
    CapabilityRequestStatus,
    ToolCall,
    ToolCallStatus,
)
from agent_platform.domain.projects import PersistedProjectManifest, ProjectRegistration
from agent_platform.domain.shared.errors import DomainError, ErrorCategory
from agent_platform.domain.shared.ids import new_id
from agent_platform.domain.tooling import ToolDefinition, ToolOperation
from agent_platform.domain.workflows import TaskStatus, WorkflowTask
from agent_platform.infrastructure.database.session import Database
from agent_platform.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from agent_platform.infrastructure.tooling import (
    AtomicFileTools,
    ControlledProcessRunner,
    PathGuard,
    ToolCatalog,
    ToolProcessRegistry,
)
from agent_platform.ports.event_publishing import LOCAL_AUDIT_CONSUMER, WEBSOCKET_CONSUMER


@dataclass(frozen=True, slots=True)
class ToolExecution:
    call: ToolCall
    output: dict[str, Any]


class ToolApplicationService:
    def __init__(
        self,
        database: Database,
        settings: Settings,
        catalog: ToolCatalog,
        path_guard: PathGuard,
        file_tools: AtomicFileTools,
        process_runner: ControlledProcessRunner,
        process_registry: ToolProcessRegistry,
    ) -> None:
        self._database = database
        self._settings = settings
        self._catalog = catalog
        self._path_guard = path_guard
        self._file_tools = file_tools
        self._process_runner = process_runner
        self._process_registry = process_registry

    def list_catalog(self) -> tuple[ToolDefinition, ...]:
        return self._catalog.list()

    async def request_capability(
        self,
        task_id: str,
        *,
        capability: str,
        reason: str,
        target_paths: tuple[str, ...],
        command: tuple[str, ...] | None,
        risk_level: CapabilityRisk,
        idempotency_key: str,
        correlation_id: str,
    ) -> CapabilityRequestRecord:
        now = datetime.now(UTC)
        async with self._write_uow() as uow:
            existing = await uow.governance.get_capability_request_by_key(task_id, idempotency_key)
            if existing is not None:
                if (
                    existing.capability != capability
                    or existing.reason != reason.strip()
                    or existing.target_paths != target_paths
                    or existing.command != command
                ):
                    raise _conflict(
                        "capability_request.idempotency_conflict",
                        "Capability request key was used with different parameters",
                    )
                return existing
            task, registration, _ = await self._task_context(uow, task_id)
            run = await uow.workflows.get_stage_run(task.stage_run_id)
            if run is None:
                raise RuntimeError("task stage run is missing")
            if task.status is not TaskStatus.RUNNING:
                raise _conflict(
                    "capability_request.task_not_running",
                    "Capability requests require a running task",
                )
            contract = get_stage_contract(run.stage)
            access = contract.capability_access(capability)
            if access is CapabilityAccess.DEFAULT:
                raise _conflict(
                    "capability_request.already_available",
                    "Capability is already available to the stage",
                )
            if access is CapabilityAccess.FORBIDDEN:
                raise DomainError(
                    code="capability_request.forbidden",
                    message="Capability cannot be requested for this stage",
                    category=ErrorCategory.PERMISSION,
                )
            record = CapabilityRequestRecord(
                schema_version=1,
                id=new_id("capreq"),
                project_id=registration.project.id,
                workflow_id=task.workflow_id,
                stage_run_id=task.stage_run_id,
                task_id=task.id,
                stage=run.stage,
                capability=capability,
                reason=reason.strip(),
                target_paths=target_paths,
                command=command,
                status=CapabilityRequestStatus.PENDING,
                risk_level=risk_level.value,
                idempotency_key=idempotency_key,
                version=1,
                requested_at=now,
            )
            approval = Approval(
                schema_version=1,
                id=new_id("approval"),
                project_id=record.project_id,
                workflow_id=record.workflow_id,
                kind=ApprovalKind.CAPABILITY,
                target_id=record.id,
                status=ApprovalStatus.PENDING,
                version=1,
                requested_at=now,
            )
            await uow.governance.add_capability_request(record)
            await uow.governance.add_approval(approval)
            await _append_event(
                uow,
                event_type="capability.requested",
                correlation_id=correlation_id,
                occurred_at=now,
                project_id=record.project_id,
                workflow_id=record.workflow_id,
                task_id=record.task_id,
                payload={
                    "request_id": record.id,
                    "capability": record.capability,
                    "risk_level": record.risk_level,
                },
            )
            await uow.commit()
        return record

    async def list_capability_requests(
        self,
        workflow_id: str,
        *,
        status: CapabilityRequestStatus | None = None,
    ) -> tuple[CapabilityRequestRecord, ...]:
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            if await uow.workflows.get(workflow_id) is None:
                raise _not_found("workflow", "Workflow was not found")
            return await uow.governance.list_capability_requests(workflow_id, status=status)

    async def decide_capability(
        self,
        request_id: str,
        *,
        approved: bool,
        expected_version: int,
        reason: str | None,
        correlation_id: str,
    ) -> CapabilityRequestRecord:
        now = datetime.now(UTC)
        status = CapabilityRequestStatus.APPROVED if approved else CapabilityRequestStatus.REJECTED
        approval_status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        async with self._write_uow() as uow:
            current = await uow.governance.get_capability_request(request_id)
            if current is None:
                raise _not_found("capability_request", "Capability request was not found")
            task = await uow.workflows.get_task(current.task_id)
            if task is None or task.status is not TaskStatus.RUNNING:
                status = CapabilityRequestStatus.REJECTED
                approval_status = ApprovalStatus.REJECTED
                reason = reason or "task_not_running"
            decided = await uow.governance.decide_capability_request(
                request_id,
                status,
                expected_version=expected_version,
                decided_at=now,
                reason=reason.strip() if reason else None,
            )
            approval = await uow.governance.get_approval_for_target(
                ApprovalKind.CAPABILITY, request_id
            )
            if approval is None:
                raise RuntimeError("capability approval is missing")
            await uow.governance.decide_approval(
                approval.id,
                approval_status,
                expected_version=approval.version,
                decided_at=now,
                reason=reason.strip() if reason else None,
            )
            await _append_event(
                uow,
                event_type="capability.decided",
                correlation_id=correlation_id,
                occurred_at=now,
                project_id=decided.project_id,
                workflow_id=decided.workflow_id,
                task_id=decided.task_id,
                payload={"request_id": decided.id, "status": decided.status.value},
            )
            await uow.commit()
        return decided

    async def execute(
        self,
        task_id: str,
        *,
        tool_name: str,
        idempotency_key: str,
        arguments: dict[str, Any],
        timeout_seconds: int,
        correlation_id: str,
    ) -> ToolExecution:
        tool = self._catalog.get(tool_name)
        if timeout_seconds > tool.max_timeout_seconds:
            raise _invalid("tool.timeout_too_large", "Tool timeout exceeds catalog limit")
        arguments_hash = _arguments_hash(arguments)
        now = datetime.now(UTC)
        capability_request: CapabilityRequestRecord | None = None
        async with self._write_uow() as uow:
            existing = await uow.governance.get_tool_call_by_key(task_id, idempotency_key)
            if existing is not None:
                if existing.tool_name != tool_name or existing.arguments_hash != arguments_hash:
                    raise _conflict(
                        "tool.idempotency_conflict",
                        "Tool key was used with different parameters",
                    )
                return ToolExecution(call=existing, output={})
            task, registration, persisted_manifest = await self._task_context(uow, task_id)
            run = await uow.workflows.get_stage_run(task.stage_run_id)
            if run is None:
                raise RuntimeError("task stage run is missing")
            if task.status is not TaskStatus.RUNNING:
                raise _conflict("tool.task_not_running", "Tool calls require a running task")
            if run.state not in {StageRunState.DISCUSSING, StageRunState.PRODUCING}:
                raise _conflict("tool.stage_not_executing", "Stage does not allow tool execution")
            access = get_stage_contract(run.stage).capability_access(tool.capability)
            approved_capabilities: tuple[str, ...] = ()
            if access is CapabilityAccess.REQUIRES_APPROVAL:
                capability_request = await uow.governance.find_approved_capability(
                    task.id, tool.capability
                )
                if capability_request is not None:
                    approved_capabilities = (tool.capability,)
            self._path_guard.authorize_capability(
                run.stage, tool, approved_capabilities=approved_capabilities
            )
            self._authorize_arguments(
                run.stage,
                tool,
                arguments,
                persisted_manifest,
                capability_request,
            )
            call = ToolCall(
                schema_version=1,
                id=new_id("toolcall"),
                project_id=registration.project.id,
                workflow_id=task.workflow_id,
                stage_run_id=task.stage_run_id,
                task_id=task.id,
                tool_name=tool.name,
                capability=tool.capability,
                idempotency_key=idempotency_key,
                arguments_hash=arguments_hash,
                status=ToolCallStatus.RUNNING,
                capability_request_id=(
                    capability_request.id if capability_request is not None else None
                ),
                started_at=now,
            )
            await uow.governance.add_tool_call(call)
            await _append_event(
                uow,
                event_type="tool.started",
                correlation_id=correlation_id,
                occurred_at=now,
                project_id=call.project_id,
                workflow_id=call.workflow_id,
                task_id=call.task_id,
                payload={"tool_call_id": call.id, "tool_name": call.tool_name},
                actor_type=ActorType.TOOL,
                source=EventSource.TOOL,
            )
            await uow.commit()
        workspace_root = Path(registration.workspace.root_path)
        try:
            output, audit_result = await self._run_tool(
                call,
                tool,
                workspace_root,
                persisted_manifest,
                arguments,
                timeout_seconds,
            )
            possible_error = audit_result.get("error_code")
            error_code = possible_error if isinstance(possible_error, str) else None
            status = ToolCallStatus.FAILED if error_code is not None else ToolCallStatus.SUCCEEDED
        except asyncio.CancelledError:
            await self._finish_call(
                call,
                ToolCallStatus.CANCELLED,
                {},
                "tool.cancelled",
                correlation_id,
            )
            raise
        except DomainError as error:
            status = (
                ToolCallStatus.TIMED_OUT
                if error.code == "tool.command_timed_out"
                else ToolCallStatus.FAILED
            )
            error_code = error.code
            output = {"error_code": error.code}
            audit_result = {"error_code": error.code}
        finished = await self._finish_call(
            call,
            status,
            audit_result,
            error_code,
            correlation_id,
        )
        return ToolExecution(call=finished, output=output)

    async def list_tool_calls(self, workflow_id: str) -> tuple[ToolCall, ...]:
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            if await uow.workflows.get(workflow_id) is None:
                raise _not_found("workflow", "Workflow was not found")
            return await uow.governance.list_tool_calls(workflow_id)

    async def cancel_call(self, call_id: str, *, correlation_id: str) -> ToolCall:
        cancelled = await self._process_registry.cancel(call_id)
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            call = await uow.governance.get_tool_call(call_id)
        if call is None:
            raise _not_found("tool_call", "Tool call was not found")
        if call.status is not ToolCallStatus.RUNNING:
            raise _conflict("tool.not_cancellable", "Tool call is already terminal")
        if not cancelled and call.status is ToolCallStatus.RUNNING:
            error_code = "tool.execution_unavailable"
        else:
            error_code = "tool.cancelled"
        return await self._finish_call(
            call,
            ToolCallStatus.CANCELLED,
            {},
            error_code,
            correlation_id,
        )

    async def cancel_all(self) -> None:
        await self._process_registry.cancel_all()

    async def _task_context(
        self,
        uow: SqlAlchemyUnitOfWork,
        task_id: str,
    ) -> tuple[WorkflowTask, ProjectRegistration, PersistedProjectManifest]:
        task = await uow.workflows.get_task(task_id)
        if task is None:
            raise _not_found("task", "Task was not found")
        workflow = await uow.workflows.get(task.workflow_id)
        if workflow is None:
            raise RuntimeError("task workflow is missing")
        registration = await uow.projects.get(workflow.project_id)
        manifest = await uow.projects.get_manifest(workflow.project_id)
        if registration is None or manifest is None:
            raise RuntimeError("task project context is incomplete")
        return task, registration, manifest

    def _authorize_arguments(
        self,
        stage: Any,
        tool: ToolDefinition,
        arguments: dict[str, Any],
        persisted_manifest: PersistedProjectManifest,
        capability_request: CapabilityRequestRecord | None,
    ) -> None:
        manifest = persisted_manifest.manifest
        if tool.operation is ToolOperation.COMMAND:
            _require_keys(arguments, {"command_index"})
            command_index = _integer_argument(arguments, "command_index", minimum=0)
            command = self._process_runner.command_for(manifest, tool.name, command_index)
            if capability_request is not None and (
                capability_request.command is None or capability_request.command != command.argv
            ):
                raise DomainError(
                    code="tool.command_not_approved",
                    message="Project command is outside the approved capability request",
                    category=ErrorCategory.PERMISSION,
                )
            return
        allowed = {"path"}
        if tool.operation is ToolOperation.WRITE:
            allowed.update({"content", "expected_hash"})
        elif tool.operation is ToolOperation.DELETE:
            allowed.add("expected_hash")
        _require_keys(arguments, allowed)
        path = _string_argument(arguments, "path")
        self._path_guard.authorize_path(stage, tool, path, manifest)
        if capability_request is not None and not _path_approved(
            path, capability_request.target_paths
        ):
            raise DomainError(
                code="tool.path_not_approved",
                message="Project path is outside the approved capability request",
                category=ErrorCategory.PERMISSION,
            )

    async def _run_tool(
        self,
        call: ToolCall,
        tool: ToolDefinition,
        workspace_root: Path,
        persisted_manifest: PersistedProjectManifest,
        arguments: dict[str, Any],
        timeout_seconds: int,
    ) -> tuple[dict[str, Any], dict[str, object]]:
        if tool.operation is ToolOperation.COMMAND:
            command_index = _integer_argument(arguments, "command_index", minimum=0)
            process_result, stdout, stderr = await self._process_runner.run(
                call.id,
                workspace_root,
                persisted_manifest.manifest,
                tool_name=tool.name,
                command_index=command_index,
                timeout_seconds=timeout_seconds,
            )
            audit = process_result.model_dump(mode="json")
            output = {
                **audit,
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
            }
            if process_result.exit_code != 0:
                audit["error_code"] = "tool.command_failed"
            return output, audit
        path = _string_argument(arguments, "path")
        if tool.operation is ToolOperation.READ:
            file_result, payload = await asyncio.to_thread(
                self._file_tools.read, workspace_root, path
            )
            try:
                content = payload.decode("utf-8")
            except UnicodeDecodeError:
                raise _invalid("tool.file_not_text", "Project file is not UTF-8 text") from None
            audit = file_result.model_dump(mode="json")
            return {**audit, "content": content}, audit
        if tool.operation is ToolOperation.WRITE:
            content = _string_argument(arguments, "content", allow_empty=True)
            expected_hash = _optional_hash(arguments.get("expected_hash"))
            file_result = await asyncio.to_thread(
                self._file_tools.write,
                workspace_root,
                path,
                content.encode("utf-8"),
                expected_hash=expected_hash,
            )
        elif tool.operation is ToolOperation.CREATE_DIRECTORY:
            file_result = await asyncio.to_thread(
                self._file_tools.create_directory, workspace_root, path
            )
        else:
            expected_hash = _required_hash(arguments.get("expected_hash"))
            file_result = await asyncio.to_thread(
                self._file_tools.delete,
                workspace_root,
                path,
                expected_hash=expected_hash,
            )
        audit = file_result.model_dump(mode="json")
        return audit, audit

    async def _finish_call(
        self,
        call: ToolCall,
        status: ToolCallStatus,
        result: dict[str, object],
        error_code: str | None,
        correlation_id: str,
    ) -> ToolCall:
        now = datetime.now(UTC)
        async with self._write_uow() as uow:
            finished = await uow.governance.finish_tool_call(
                call.id,
                status,
                completed_at=now,
                result=result,
                error_code=error_code,
            )
            await _append_event(
                uow,
                event_type="tool.completed",
                correlation_id=correlation_id,
                occurred_at=now,
                project_id=finished.project_id,
                workflow_id=finished.workflow_id,
                task_id=finished.task_id,
                payload={
                    "tool_call_id": finished.id,
                    "tool_name": finished.tool_name,
                    "status": finished.status.value,
                    "error_code": finished.error_code,
                },
                actor_type=ActorType.TOOL,
                source=EventSource.TOOL,
            )
            await uow.commit()
        return finished

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
    task_id: str | None = None,
    actor_type: ActorType = ActorType.USER,
    source: EventSource = EventSource.BACKEND,
) -> None:
    await uow.events.append(
        envelope=EventEnvelope(
            schema_version=1,
            event_type=event_type,
            correlation_id=correlation_id,
            actor=ActorRef(
                type=actor_type,
                id="tool_runtime" if actor_type is ActorType.TOOL else "user_local",
            ),
            source=source,
            occurred_at=occurred_at,
            project_id=project_id,
            workflow_id=workflow_id,
            task_id=task_id,
            payload=payload,
        ),
        aggregate_type="workflow",
        aggregate_id=workflow_id,
    )


def _arguments_hash(arguments: dict[str, Any]) -> str:
    payload = json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _require_keys(arguments: dict[str, Any], allowed: set[str]) -> None:
    required = {"path"} if "path" in allowed else {"command_index"}
    if not required.issubset(arguments) or not set(arguments).issubset(allowed):
        raise _invalid("tool.arguments_invalid", "Tool arguments do not match the catalog")


def _string_argument(arguments: dict[str, Any], key: str, *, allow_empty: bool = False) -> str:
    value = arguments.get(key)
    if type(value) is not str or (not allow_empty and not value):
        raise _invalid("tool.arguments_invalid", "Tool arguments do not match the catalog")
    return value


def _integer_argument(arguments: dict[str, Any], key: str, *, minimum: int) -> int:
    value = arguments.get(key)
    if type(value) is not int or value < minimum:
        raise _invalid("tool.arguments_invalid", "Tool arguments do not match the catalog")
    return value


def _optional_hash(value: object) -> str | None:
    if value is None:
        return None
    return _required_hash(value)


def _required_hash(value: object) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise _invalid("tool.arguments_invalid", "Tool arguments do not match the catalog")
    return value


def _path_approved(path: str, targets: tuple[str, ...]) -> bool:
    return any(path == target or path.startswith(f"{target}/") for target in targets)


def _invalid(code: str, message: str) -> DomainError:
    return DomainError(code=code, message=message, category=ErrorCategory.INVALID_INPUT)


def _conflict(code: str, message: str) -> DomainError:
    return DomainError(code=code, message=message, category=ErrorCategory.CONFLICT)


def _not_found(entity: str, message: str) -> DomainError:
    return DomainError(
        code=f"{entity}.not_found",
        message=message,
        category=ErrorCategory.NOT_FOUND,
    )
