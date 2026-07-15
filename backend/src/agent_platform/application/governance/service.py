from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from agent_platform.application.model_runtime import AgentRunRegistry
from agent_platform.config.settings import Settings
from agent_platform.domain.contracts import STAGE_ORDER, Stage, StageRunState, successor
from agent_platform.domain.events import ActorRef, ActorType, EventEnvelope, EventSource
from agent_platform.domain.governance import (
    Approval,
    ApprovalKind,
    ApprovalStatus,
    Artifact,
    ArtifactStatus,
    ArtifactVersion,
    ChangeRequest,
    ChangeRequestStatus,
    ExecutionMode,
    GateIssue,
    GateIssueSeverity,
    GateResolution,
    GateStatus,
    HandoffPacket,
    HandoffStatus,
    QualityGateRun,
    RecoveryRecord,
    RecoveryStatus,
    ToolCallStatus,
)
from agent_platform.domain.model_runtime import AgentRunStatus
from agent_platform.domain.projects import (
    CheckpointReason,
    ProjectCheckpoint,
    ProjectManifest,
    ProjectRegistration,
)
from agent_platform.domain.shared.errors import DomainError, ErrorCategory
from agent_platform.domain.shared.ids import new_id
from agent_platform.domain.workflows import (
    StageRun,
    TaskStatus,
    Workflow,
    WorkflowStatus,
    require_stage_transition,
)
from agent_platform.infrastructure.database.session import Database
from agent_platform.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from agent_platform.infrastructure.projects.checkpoints import CheckpointStore
from agent_platform.infrastructure.tooling import AtomicFileTools, ToolProcessRegistry
from agent_platform.infrastructure.workers.supervisor import WorkerSupervisor
from agent_platform.ports.event_publishing import LOCAL_AUDIT_CONSUMER, WEBSOCKET_CONSUMER


@dataclass(frozen=True, slots=True)
class ArtifactInventory:
    artifacts: tuple[Artifact, ...]
    versions: tuple[ArtifactVersion, ...]


@dataclass(frozen=True, slots=True)
class GateEvaluation:
    gate: QualityGateRun
    approval: Approval | None
    handoff: HandoffPacket | None
    change_request: ChangeRequest | None


@dataclass(frozen=True, slots=True)
class ApprovalDecisionExecution:
    approval: Approval
    gate: QualityGateRun
    handoff: HandoffPacket | None
    change_request: ChangeRequest | None


class GovernanceApplicationService:
    def __init__(
        self,
        database: Database,
        settings: Settings,
        file_tools: AtomicFileTools,
        agent_run_registry: AgentRunRegistry,
        tool_process_registry: ToolProcessRegistry,
        worker_supervisor: WorkerSupervisor,
    ) -> None:
        self._database = database
        self._settings = settings
        self._file_tools = file_tools
        self._agent_run_registry = agent_run_registry
        self._tool_process_registry = tool_process_registry
        self._worker_supervisor = worker_supervisor

    async def set_execution_mode(
        self,
        workflow_id: str,
        mode: ExecutionMode,
        *,
        expected_version: int,
        correlation_id: str,
    ) -> Workflow:
        now = datetime.now(UTC)
        async with self._write_uow() as uow:
            workflow = await uow.workflows.get(workflow_id)
            if workflow is None:
                raise _not_found("workflow", "Workflow was not found")
            await uow.governance.set_workflow_mode(
                workflow_id,
                mode,
                expected_version=expected_version,
                updated_at=now,
            )
            updated = await uow.workflows.get(workflow_id)
            if updated is None:
                raise RuntimeError("workflow disappeared after mode update")
            await _append_event(
                uow,
                event_type="workflow.mode_changed",
                correlation_id=correlation_id,
                occurred_at=now,
                project_id=workflow.project_id,
                workflow_id=workflow.id,
                payload={"execution_mode": mode.value},
            )
            await uow.commit()
        return updated

    async def create_artifact_version(
        self,
        stage_run_id: str,
        *,
        name: str,
        relative_path: str,
        correlation_id: str,
    ) -> tuple[Artifact, ArtifactVersion]:
        now = datetime.now(UTC)
        async with self._write_uow() as uow:
            run = await uow.workflows.get_stage_run(stage_run_id)
            if run is None:
                raise _not_found("stage_run", "Stage run was not found")
            workflow = await uow.workflows.get(run.workflow_id)
            if workflow is None:
                raise RuntimeError("stage run workflow is missing")
            if workflow.current_stage is not run.stage:
                raise _conflict("artifact.stage_not_current", "Artifact stage is not current")
            if run.state not in {
                StageRunState.PRODUCING,
                StageRunState.P2R_REVIEWING,
                StageRunState.QUALITY_CHECKING,
                StageRunState.NEEDS_FIX,
            }:
                raise _conflict("artifact.stage_not_producing", "Stage is not producing artifacts")
            expected_prefix = f"artifacts/{run.stage.value}"
            if not (
                relative_path == expected_prefix or relative_path.startswith(f"{expected_prefix}/")
            ):
                raise DomainError(
                    code="artifact.path_out_of_scope",
                    message="Artifact path does not belong to the stage",
                    category=ErrorCategory.PERMISSION,
                )
            registration = await uow.projects.get(workflow.project_id)
            if registration is None:
                raise RuntimeError("artifact project registration is missing")
            file_result, _ = await asyncio.to_thread(
                self._file_tools.read,
                Path(registration.workspace.root_path),
                relative_path,
            )
            artifact = await uow.governance.find_artifact(workflow.id, run.stage, name.strip())
            if artifact is None:
                artifact = Artifact(
                    schema_version=1,
                    id=new_id("artifact"),
                    project_id=workflow.project_id,
                    workflow_id=workflow.id,
                    stage=run.stage,
                    name=name.strip(),
                    relative_path=relative_path,
                    created_at=now,
                )
                await uow.governance.add_artifact(artifact)
            elif artifact.relative_path != relative_path:
                raise _conflict(
                    "artifact.path_conflict", "Artifact name is registered to another path"
                )
            latest = await uow.governance.latest_artifact_version(artifact.id)
            if (
                latest is not None
                and latest.content_hash == file_result.content_hash
                and latest.byte_size == file_result.byte_size
                and latest.status in {ArtifactStatus.DRAFT, ArtifactStatus.LOCKED}
            ):
                return artifact, latest
            version = ArtifactVersion(
                schema_version=1,
                id=new_id("artifactv"),
                artifact_id=artifact.id,
                stage_run_id=run.id,
                version=1 if latest is None else latest.version + 1,
                content_hash=file_result.content_hash,
                byte_size=file_result.byte_size,
                status=ArtifactStatus.DRAFT,
                supersedes_id=latest.id if latest is not None else None,
                created_at=now,
            )
            await uow.governance.add_artifact_version(version)
            await _append_event(
                uow,
                event_type="artifact.version_created",
                correlation_id=correlation_id,
                occurred_at=now,
                project_id=workflow.project_id,
                workflow_id=workflow.id,
                payload={
                    "artifact_id": artifact.id,
                    "artifact_version_id": version.id,
                    "stage": run.stage.value,
                    "version": version.version,
                    "content_hash": version.content_hash,
                },
            )
            await uow.commit()
        return artifact, version

    async def list_artifacts(self, workflow_id: str) -> ArtifactInventory:
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            if await uow.workflows.get(workflow_id) is None:
                raise _not_found("workflow", "Workflow was not found")
            return ArtifactInventory(
                artifacts=await uow.governance.list_artifacts(workflow_id),
                versions=await uow.governance.list_artifact_versions(workflow_id),
            )

    async def evaluate_gate(
        self,
        stage_run_id: str,
        *,
        artifact_version_ids: tuple[str, ...],
        correlation_id: str,
    ) -> GateEvaluation:
        if not artifact_version_ids or len(set(artifact_version_ids)) != len(artifact_version_ids):
            raise _invalid(
                "quality_gate.artifacts_invalid",
                "Quality gate requires unique artifact versions",
            )
        now = datetime.now(UTC)
        async with self._write_uow() as uow:
            run, workflow, registration = await self._gate_context(uow, stage_run_id)
            if run.state is not StageRunState.QUALITY_CHECKING:
                raise _conflict(
                    "quality_gate.stage_not_checking",
                    "Quality gate requires quality_checking state",
                )
            room = await uow.workflows.get_room_for_stage_run(run.id)
            manifest = await uow.projects.get_manifest(workflow.project_id)
            if room is None or manifest is None:
                raise RuntimeError("quality gate context is incomplete")
            issues: list[GateIssue] = []
            versions: list[ArtifactVersion] = []
            for version_id in artifact_version_ids:
                version = await uow.governance.get_artifact_version(version_id)
                if version is None:
                    issues.append(_issue("quality_gate.artifact_missing", "Artifact is missing"))
                    continue
                artifact = await uow.governance.get_artifact(version.artifact_id)
                if (
                    artifact is None
                    or artifact.workflow_id != workflow.id
                    or artifact.stage is not run.stage
                    or version.stage_run_id != run.id
                    or version.status is not ArtifactStatus.DRAFT
                ):
                    issues.append(
                        _issue(
                            "quality_gate.artifact_invalid",
                            "Artifact version is not a current stage draft",
                        )
                    )
                    continue
                current, _ = await asyncio.to_thread(
                    self._file_tools.read,
                    Path(registration.workspace.root_path),
                    artifact.relative_path,
                )
                if (
                    current.content_hash != version.content_hash
                    or current.byte_size != version.byte_size
                ):
                    issues.append(
                        _issue(
                            "quality_gate.artifact_changed",
                            "Artifact content changed after version creation",
                        )
                    )
                    continue
                versions.append(version)
            formal_runs = tuple(
                run_record
                for run_record in await uow.model_runtime.list_runs(room.id)
                if run_record.formal
            )
            if not formal_runs:
                issues.append(
                    _issue(
                        "quality_gate.formal_run_required",
                        "Formal Primary and dual-review run is required",
                    )
                )
            elif formal_runs[-1].status is not AgentRunStatus.SUCCEEDED:
                issues.append(
                    _issue(
                        "quality_gate.formal_run_failed",
                        "Latest formal agent run did not succeed",
                    )
                )
            tasks = await uow.workflows.list_tasks(workflow.id)
            if any(task.status in {TaskStatus.QUEUED, TaskStatus.RUNNING} for task in tasks):
                issues.append(
                    _issue(
                        "quality_gate.tasks_active",
                        "Workflow tasks must be terminal before gate evaluation",
                    )
                )
            if await uow.projects.list_open_file_conflicts(workflow.project_id):
                issues.append(
                    _issue(
                        "quality_gate.conflicts_open",
                        "Open file conflicts block the quality gate",
                    )
                )
            if run.stage in {Stage.BUILDER, Stage.REVIEWER} and not manifest.manifest.test_commands:
                issues.append(
                    GateIssue(
                        code="quality_gate.test_command_missing",
                        severity=GateIssueSeverity.WARNING,
                        message="Project manifest has no deterministic test command",
                    )
                )
            issues = list({issue.code: issue for issue in issues}.values())
            status = _gate_status(tuple(issues))
            resolution = GateResolution.PENDING
            resolved_at: datetime | None = None
            if status is GateStatus.FAIL or (
                status is GateStatus.WARNING and workflow.execution_mode is ExecutionMode.AUTONOMOUS
            ):
                resolution = GateResolution.REWRITE_REQUIRED
                resolved_at = now
            elif status is GateStatus.PASS and workflow.execution_mode is ExecutionMode.AUTONOMOUS:
                resolution = GateResolution.AUTOMATIC
                resolved_at = now
            gate = QualityGateRun(
                schema_version=1,
                id=new_id("gate"),
                project_id=workflow.project_id,
                workflow_id=workflow.id,
                stage_run_id=run.id,
                status=status,
                resolution=resolution,
                issues=tuple(issues),
                artifact_version_ids=tuple(version.id for version in versions),
                version=1,
                evaluated_at=now,
                resolved_at=resolved_at,
            )
            await uow.governance.add_gate(gate)
            approval: Approval | None = None
            handoff: HandoffPacket | None = None
            change_request: ChangeRequest | None = None
            if resolution is GateResolution.PENDING:
                require_stage_transition(run.state, StageRunState.WAITING_APPROVAL)
                updated_workflow, _, _ = await uow.workflows.transition_stage(
                    workflow.id,
                    run.id,
                    StageRunState.WAITING_APPROVAL,
                    expected_workflow_version=workflow.version,
                    expected_stage_version=run.version,
                    updated_at=now,
                )
                await uow.governance.set_workflow_status(
                    workflow.id, WorkflowStatus.WAITING_USER, updated_at=now
                )
                approval = Approval(
                    schema_version=1,
                    id=new_id("approval"),
                    project_id=workflow.project_id,
                    workflow_id=workflow.id,
                    kind=ApprovalKind.QUALITY_GATE,
                    target_id=gate.id,
                    status=ApprovalStatus.PENDING,
                    version=1,
                    requested_at=now,
                )
                await uow.governance.add_approval(approval)
                del updated_workflow
            elif resolution is GateResolution.AUTOMATIC:
                handoff = await self._finalize_gate(
                    uow,
                    gate,
                    run,
                    workflow,
                    registration.workspace.root_path,
                    manifest.manifest,
                    now,
                    correlation_id,
                )
            else:
                target_state = (
                    StageRunState.WARNING_BLOCKED
                    if status is GateStatus.WARNING
                    else StageRunState.NEEDS_FIX
                )
                require_stage_transition(run.state, target_state)
                await uow.governance.set_stage_state(run.id, target_state, updated_at=now)
                await uow.governance.set_workflow_status(
                    workflow.id,
                    (
                        WorkflowStatus.WARNING_BLOCKED
                        if target_state is StageRunState.WARNING_BLOCKED
                        else WorkflowStatus.RUNNING
                    ),
                    updated_at=now,
                )
                change_request = await self._add_gate_change_request(
                    uow, gate, run, tuple(version.id for version in versions), now
                )
            await _append_event(
                uow,
                event_type="quality_gate.evaluated",
                correlation_id=correlation_id,
                occurred_at=now,
                project_id=workflow.project_id,
                workflow_id=workflow.id,
                payload={
                    "gate_run_id": gate.id,
                    "stage_run_id": run.id,
                    "status": gate.status.value,
                    "resolution": gate.resolution.value,
                },
            )
            await uow.commit()
        return GateEvaluation(
            gate=gate,
            approval=approval,
            handoff=handoff,
            change_request=change_request,
        )

    async def list_gates(self, workflow_id: str) -> tuple[QualityGateRun, ...]:
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            if await uow.workflows.get(workflow_id) is None:
                raise _not_found("workflow", "Workflow was not found")
            return await uow.governance.list_gates(workflow_id)

    async def list_approvals(
        self, workflow_id: str, *, status: ApprovalStatus | None = None
    ) -> tuple[Approval, ...]:
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            if await uow.workflows.get(workflow_id) is None:
                raise _not_found("workflow", "Workflow was not found")
            return await uow.governance.list_approvals(workflow_id, status=status)

    async def decide_gate_approval(
        self,
        approval_id: str,
        *,
        approved: bool,
        expected_version: int,
        reason: str | None,
        correlation_id: str,
    ) -> ApprovalDecisionExecution:
        now = datetime.now(UTC)
        async with self._write_uow() as uow:
            approval = await uow.governance.get_approval(approval_id)
            if approval is None:
                raise _not_found("approval", "Approval was not found")
            if approval.kind is not ApprovalKind.QUALITY_GATE:
                raise _conflict("approval.wrong_kind", "Approval is not a quality gate approval")
            gate = await uow.governance.get_gate(approval.target_id)
            if gate is None:
                raise RuntimeError("quality gate approval target is missing")
            run, workflow, registration = await self._gate_context(uow, gate.stage_run_id)
            if run.state is not StageRunState.WAITING_APPROVAL:
                raise _conflict("approval.stage_not_waiting", "Stage is not waiting for approval")
            decision = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
            approval = await uow.governance.decide_approval(
                approval.id,
                decision,
                expected_version=expected_version,
                decided_at=now,
                reason=reason.strip() if reason else None,
            )
            handoff: HandoffPacket | None = None
            change_request: ChangeRequest | None = None
            if approved:
                if gate.status is GateStatus.FAIL:
                    raise _conflict(
                        "approval.gate_failed", "Failed quality gate cannot be approved"
                    )
                gate = await uow.governance.resolve_gate(
                    gate.id,
                    GateResolution.APPROVED,
                    expected_version=gate.version,
                    resolved_at=now,
                )
                manifest = await uow.projects.get_manifest(workflow.project_id)
                if manifest is None:
                    raise RuntimeError("quality gate manifest is missing")
                await uow.governance.set_workflow_status(
                    workflow.id, WorkflowStatus.RUNNING, updated_at=now
                )
                updated_workflow = await uow.workflows.get(workflow.id)
                if updated_workflow is None:
                    raise RuntimeError("workflow disappeared before handoff")
                handoff = await self._finalize_gate(
                    uow,
                    gate,
                    run,
                    updated_workflow,
                    registration.workspace.root_path,
                    manifest.manifest,
                    now,
                    correlation_id,
                )
            else:
                gate = await uow.governance.resolve_gate(
                    gate.id,
                    GateResolution.REWRITE_REQUIRED,
                    expected_version=gate.version,
                    resolved_at=now,
                )
                require_stage_transition(run.state, StageRunState.NEEDS_FIX)
                await uow.governance.set_stage_state(
                    run.id, StageRunState.NEEDS_FIX, updated_at=now
                )
                await uow.governance.set_workflow_status(
                    workflow.id, WorkflowStatus.RUNNING, updated_at=now
                )
                change_request = await self._add_gate_change_request(
                    uow, gate, run, gate.artifact_version_ids, now
                )
            await _append_event(
                uow,
                event_type="approval.decided",
                correlation_id=correlation_id,
                occurred_at=now,
                project_id=approval.project_id,
                workflow_id=approval.workflow_id,
                payload={
                    "approval_id": approval.id,
                    "target_id": approval.target_id,
                    "status": approval.status.value,
                },
            )
            await uow.commit()
        return ApprovalDecisionExecution(
            approval=approval,
            gate=gate,
            handoff=handoff,
            change_request=change_request,
        )

    async def list_handoffs(self, workflow_id: str) -> tuple[HandoffPacket, ...]:
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            if await uow.workflows.get(workflow_id) is None:
                raise _not_found("workflow", "Workflow was not found")
            return await uow.governance.list_handoffs(workflow_id)

    async def create_change_request(
        self,
        workflow_id: str,
        *,
        target_stage: Stage,
        reason: str,
        input_artifact_version_ids: tuple[str, ...],
        correlation_id: str,
    ) -> ChangeRequest:
        now = datetime.now(UTC)
        async with self._write_uow() as uow:
            workflow = await uow.workflows.get(workflow_id)
            if workflow is None:
                raise _not_found("workflow", "Workflow was not found")
            if STAGE_ORDER.index(target_stage) > STAGE_ORDER.index(workflow.current_stage):
                raise _invalid(
                    "change_request.target_invalid",
                    "Change request cannot target a downstream stage",
                )
            run = await uow.workflows.get_current_stage_run(workflow.id, workflow.current_stage)
            if run is None:
                raise RuntimeError("current stage run is missing")
            request = ChangeRequest(
                schema_version=1,
                id=new_id("changereq"),
                project_id=workflow.project_id,
                workflow_id=workflow.id,
                source_stage_run_id=run.id,
                target_stage=target_stage,
                reason=reason.strip(),
                status=ChangeRequestStatus.OPEN,
                input_artifact_version_ids=input_artifact_version_ids,
                created_at=now,
            )
            await uow.governance.add_change_request(request)
            affected = STAGE_ORDER[STAGE_ORDER.index(target_stage) :]
            await uow.governance.invalidate_artifacts_from_stage(
                workflow.id,
                affected,
                invalidated_at=now,
                reason=f"change_request:{request.id}",
            )
            await uow.governance.invalidate_handoffs_from_stage(
                workflow.id,
                affected,
                invalidated_at=now,
                reason=f"change_request:{request.id}",
            )
            await _append_event(
                uow,
                event_type="change_request.created",
                correlation_id=correlation_id,
                occurred_at=now,
                project_id=workflow.project_id,
                workflow_id=workflow.id,
                payload={
                    "change_request_id": request.id,
                    "target_stage": request.target_stage.value,
                },
            )
            await uow.commit()
        return request

    async def list_change_requests(self, workflow_id: str) -> tuple[ChangeRequest, ...]:
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            if await uow.workflows.get(workflow_id) is None:
                raise _not_found("workflow", "Workflow was not found")
            return await uow.governance.list_change_requests(workflow_id)

    async def control_workflow(
        self,
        workflow_id: str,
        action: str,
        *,
        expected_version: int,
        correlation_id: str,
    ) -> Workflow:
        now = datetime.now(UTC)
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            workflow = await uow.workflows.get(workflow_id)
            if workflow is None:
                raise _not_found("workflow", "Workflow was not found")
            if workflow.version != expected_version:
                raise _conflict("workflow.version_conflict", "Workflow version has changed")
            run = await uow.workflows.get_current_stage_run(workflow.id, workflow.current_stage)
            agent_run_ids = await uow.governance.active_agent_run_ids(workflow.id)
            tool_calls = await uow.governance.list_tool_calls(workflow.id)
        for run_id in agent_run_ids:
            await self._agent_run_registry.cancel(run_id)
        for call in tool_calls:
            if call.status is ToolCallStatus.RUNNING:
                await self._tool_process_registry.cancel(call.id)
        await self._worker_supervisor.stop_project(workflow.project_id)
        async with self._write_uow() as uow:
            current = await uow.workflows.get(workflow.id)
            if current is None or current.version != expected_version:
                raise _conflict("workflow.version_conflict", "Workflow version has changed")
            if action == "pause":
                if current.status not in {
                    WorkflowStatus.RUNNING,
                    WorkflowStatus.WAITING_USER,
                    WorkflowStatus.WARNING_BLOCKED,
                }:
                    raise _conflict("workflow.not_pausable", "Workflow cannot be paused")
                target_status = WorkflowStatus.PAUSED
                await uow.governance.cancel_tasks(
                    workflow.id, completed_at=now, include_queued=False
                )
            elif action == "resume":
                if current.status is not WorkflowStatus.PAUSED:
                    raise _conflict("workflow.not_resumable", "Workflow is not paused")
                target_status = WorkflowStatus.RUNNING
            elif action in {"stop", "abandon"}:
                if current.status in {
                    WorkflowStatus.COMPLETED,
                    WorkflowStatus.STOPPED,
                    WorkflowStatus.ABANDONED,
                }:
                    raise _conflict("workflow.terminal", "Workflow is already terminal")
                target_status = (
                    WorkflowStatus.STOPPED if action == "stop" else WorkflowStatus.ABANDONED
                )
                await uow.governance.cancel_tasks(workflow.id, completed_at=now)
                if run is not None:
                    await uow.governance.set_stage_state(
                        run.id,
                        (StageRunState.CANCELLED if action == "stop" else StageRunState.ABANDONED),
                        updated_at=now,
                    )
                    await uow.governance.archive_stage_room(run.id, updated_at=now)
            else:
                raise _invalid("workflow.action_invalid", "Workflow action is invalid")
            await uow.governance.cancel_agent_runs(workflow.id, completed_at=now)
            await uow.governance.cancel_tool_calls(workflow.id, completed_at=now)
            await uow.governance.set_workflow_status(workflow.id, target_status, updated_at=now)
            updated = await uow.workflows.get(workflow.id)
            if updated is None:
                raise RuntimeError("workflow disappeared after control action")
            await _append_event(
                uow,
                event_type=f"workflow.{action}d" if action != "stop" else "workflow.stopped",
                correlation_id=correlation_id,
                occurred_at=now,
                project_id=workflow.project_id,
                workflow_id=workflow.id,
                payload={"status": updated.status.value},
            )
            await uow.commit()
        return updated

    async def recover_incomplete_workflows(self) -> tuple[RecoveryRecord, ...]:
        now = datetime.now(UTC)
        async with self._write_uow() as uow:
            recoveries = await uow.governance.recover_incomplete(detected_at=now)
            for recovery in recoveries:
                await _append_event(
                    uow,
                    event_type="recovery.detected",
                    correlation_id=recovery.id,
                    occurred_at=now,
                    project_id=recovery.project_id,
                    workflow_id=recovery.workflow_id,
                    payload={
                        "recovery_id": recovery.id,
                        "interrupted_tasks": recovery.interrupted_tasks,
                        "interrupted_agent_runs": recovery.interrupted_agent_runs,
                        "interrupted_tool_calls": recovery.interrupted_tool_calls,
                    },
                    actor_type=ActorType.SYSTEM,
                )
            await uow.commit()
        return recoveries

    async def list_recoveries(self) -> tuple[RecoveryRecord, ...]:
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            return await uow.governance.list_recoveries()

    async def resolve_recovery(
        self,
        recovery_id: str,
        *,
        resume: bool,
        correlation_id: str,
    ) -> RecoveryRecord:
        now = datetime.now(UTC)
        async with self._write_uow() as uow:
            current = await uow.governance.get_recovery(recovery_id)
            if current is None:
                raise _not_found("recovery", "Recovery record was not found")
            workflow = await uow.workflows.get(current.workflow_id)
            if workflow is None:
                raise RuntimeError("recovery workflow is missing")
            if resume:
                if workflow.status is not WorkflowStatus.INTERRUPTED:
                    raise _conflict(
                        "recovery.workflow_not_interrupted",
                        "Workflow is not interrupted",
                    )
                await uow.governance.set_workflow_status(
                    workflow.id, WorkflowStatus.RUNNING, updated_at=now
                )
                if current.stage_run_id is not None:
                    await uow.governance.set_stage_state(
                        current.stage_run_id, StageRunState.DISCUSSING, updated_at=now
                    )
                resolution = RecoveryStatus.RESUMED
                event_type = "recovery.resumed"
            else:
                await uow.governance.set_workflow_status(
                    workflow.id, WorkflowStatus.STOPPED, updated_at=now
                )
                if current.stage_run_id is not None:
                    await uow.governance.set_stage_state(
                        current.stage_run_id, StageRunState.CANCELLED, updated_at=now
                    )
                    await uow.governance.archive_stage_room(current.stage_run_id, updated_at=now)
                resolution = RecoveryStatus.DISCARDED
                event_type = "recovery.discarded"
            recovery = await uow.governance.resolve_recovery(
                current.id, resolution, resolved_at=now
            )
            await _append_event(
                uow,
                event_type=event_type,
                correlation_id=correlation_id,
                occurred_at=now,
                project_id=recovery.project_id,
                workflow_id=recovery.workflow_id,
                payload={"recovery_id": recovery.id},
                actor_type=ActorType.SYSTEM,
            )
            await uow.commit()
        return recovery

    async def _gate_context(
        self,
        uow: SqlAlchemyUnitOfWork,
        stage_run_id: str,
    ) -> tuple[StageRun, Workflow, ProjectRegistration]:
        run = await uow.workflows.get_stage_run(stage_run_id)
        if run is None:
            raise _not_found("stage_run", "Stage run was not found")
        workflow = await uow.workflows.get(run.workflow_id)
        if workflow is None:
            raise RuntimeError("stage run workflow is missing")
        if workflow.current_stage is not run.stage:
            raise _conflict("stage_run.not_current", "Stage run is not current")
        registration = await uow.projects.get(workflow.project_id)
        if registration is None:
            raise RuntimeError("quality gate project registration is missing")
        return run, workflow, registration

    async def _finalize_gate(
        self,
        uow: SqlAlchemyUnitOfWork,
        gate: QualityGateRun,
        run: StageRun,
        workflow: Workflow,
        workspace_root: str,
        manifest: ProjectManifest,
        now: datetime,
        correlation_id: str,
    ) -> HandoffPacket:
        versions: list[ArtifactVersion] = []
        for version_id in gate.artifact_version_ids:
            version = await uow.governance.get_artifact_version(version_id)
            if version is None or version.status is not ArtifactStatus.DRAFT:
                raise _conflict(
                    "quality_gate.artifact_not_lockable",
                    "Gate artifact is no longer lockable",
                )
            artifact = await uow.governance.get_artifact(version.artifact_id)
            if artifact is None:
                raise RuntimeError("gate artifact is missing")
            current, _ = await asyncio.to_thread(
                self._file_tools.read, Path(workspace_root), artifact.relative_path
            )
            if current.content_hash != version.content_hash:
                raise _conflict(
                    "quality_gate.artifact_changed",
                    "Gate artifact changed before handoff",
                )
            versions.append(version)
        checkpoint = await asyncio.to_thread(
            self._checkpoint_store().create,
            Path(workspace_root),
            manifest,
            reason=CheckpointReason.MANUAL,
            created_at=now,
        )
        await uow.projects.record_checkpoint(checkpoint)
        await uow.governance.lock_artifact_versions(
            gate.artifact_version_ids,
            checkpoint_id=checkpoint.id,
            locked_at=now,
        )
        current_workflow = await uow.workflows.get(workflow.id)
        current_run = await uow.workflows.get_stage_run(run.id)
        if current_workflow is None or current_run is None:
            raise RuntimeError("workflow disappeared before finalization")
        if current_run.state is StageRunState.QUALITY_CHECKING:
            require_stage_transition(current_run.state, StageRunState.WAITING_APPROVAL)
            current_workflow, current_run, _ = await uow.workflows.transition_stage(
                workflow.id,
                run.id,
                StageRunState.WAITING_APPROVAL,
                expected_workflow_version=current_workflow.version,
                expected_stage_version=current_run.version,
                updated_at=now,
            )
        require_stage_transition(current_run.state, StageRunState.HANDOFF_READY)
        current_workflow, current_run, _ = await uow.workflows.transition_stage(
            workflow.id,
            run.id,
            StageRunState.HANDOFF_READY,
            expected_workflow_version=current_workflow.version,
            expected_stage_version=current_run.version,
            updated_at=now,
        )
        handoff = _handoff_packet(
            gate,
            run,
            checkpoint,
            tuple(version.id for version in versions),
            now,
        )
        await uow.governance.add_handoff(handoff)
        require_stage_transition(current_run.state, StageRunState.COMPLETED)
        completed_workflow, completed_run, unlocked = await uow.workflows.transition_stage(
            workflow.id,
            run.id,
            StageRunState.COMPLETED,
            expected_workflow_version=current_workflow.version,
            expected_stage_version=current_run.version,
            updated_at=now,
        )
        await _append_event(
            uow,
            event_type="handoff.created",
            correlation_id=correlation_id,
            occurred_at=now,
            project_id=workflow.project_id,
            workflow_id=workflow.id,
            payload={
                "handoff_id": handoff.id,
                "gate_run_id": gate.id,
                "checkpoint_id": checkpoint.id,
                "from_stage": run.stage.value,
                "to_stage": handoff.to_stage.value if handoff.to_stage else None,
                "completed_stage_run_id": completed_run.id,
                "unlocked_stage_run_id": unlocked.id if unlocked else None,
                "workflow_status": completed_workflow.status.value,
            },
        )
        return handoff

    async def _add_gate_change_request(
        self,
        uow: SqlAlchemyUnitOfWork,
        gate: QualityGateRun,
        run: StageRun,
        artifact_version_ids: tuple[str, ...],
        now: datetime,
    ) -> ChangeRequest:
        reason = "; ".join(issue.code for issue in gate.issues) or "quality_gate_rewrite"
        request = ChangeRequest(
            schema_version=1,
            id=new_id("changereq"),
            project_id=gate.project_id,
            workflow_id=gate.workflow_id,
            source_stage_run_id=run.id,
            target_stage=run.stage,
            gate_run_id=gate.id,
            reason=reason,
            status=ChangeRequestStatus.OPEN,
            input_artifact_version_ids=artifact_version_ids,
            created_at=now,
        )
        await uow.governance.add_change_request(request)
        return request

    def _checkpoint_store(self) -> CheckpointStore:
        return CheckpointStore(
            self._settings.snapshot_root,
            max_files=self._settings.checkpoint_max_files,
            max_file_bytes=self._settings.checkpoint_max_file_bytes,
            max_total_bytes=self._settings.checkpoint_max_total_bytes,
        )

    def _write_uow(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(
            self._database.sessions,
            delivery_targets=(LOCAL_AUDIT_CONSUMER, WEBSOCKET_CONSUMER),
            write=True,
            write_lock=self._database.write_lock,
        )


def _gate_status(issues: tuple[GateIssue, ...]) -> GateStatus:
    if any(issue.severity is GateIssueSeverity.ERROR for issue in issues):
        return GateStatus.FAIL
    if issues:
        return GateStatus.WARNING
    return GateStatus.PASS


def _issue(code: str, message: str) -> GateIssue:
    return GateIssue(code=code, severity=GateIssueSeverity.ERROR, message=message)


def _handoff_packet(
    gate: QualityGateRun,
    run: StageRun,
    checkpoint: ProjectCheckpoint,
    artifact_version_ids: tuple[str, ...],
    created_at: datetime,
) -> HandoffPacket:
    to_stage = successor(run.stage)
    document = {
        "schema_version": 1,
        "workflow_id": gate.workflow_id,
        "from_stage_run_id": run.id,
        "from_stage": run.stage.value,
        "to_stage": to_stage.value if to_stage else None,
        "gate_run_id": gate.id,
        "checkpoint_id": checkpoint.id,
        "checkpoint_hash": checkpoint.content_hash,
        "artifact_version_ids": list(artifact_version_ids),
    }
    canonical = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return HandoffPacket(
        schema_version=1,
        id=new_id("handoff"),
        project_id=gate.project_id,
        workflow_id=gate.workflow_id,
        from_stage_run_id=run.id,
        from_stage=run.stage,
        to_stage=to_stage,
        gate_run_id=gate.id,
        checkpoint_id=checkpoint.id,
        artifact_version_ids=artifact_version_ids,
        content_hash=hashlib.sha256(canonical).hexdigest(),
        status=HandoffStatus.ACTIVE,
        created_at=created_at,
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
    actor_type: ActorType = ActorType.USER,
) -> None:
    await uow.events.append(
        envelope=EventEnvelope(
            schema_version=1,
            event_type=event_type,
            correlation_id=correlation_id,
            actor=ActorRef(
                type=actor_type,
                id="system_recovery" if actor_type is ActorType.SYSTEM else "user_local",
            ),
            source=EventSource.BACKEND,
            occurred_at=occurred_at,
            project_id=project_id,
            workflow_id=workflow_id,
            payload=payload,
        ),
        aggregate_type="workflow",
        aggregate_id=workflow_id,
    )


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
