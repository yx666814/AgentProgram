from __future__ import annotations

from copy import deepcopy
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_platform.domain.contracts import Stage, StageRunState
from agent_platform.domain.governance import (
    Approval,
    ApprovalKind,
    ApprovalStatus,
    Artifact,
    ArtifactStatus,
    ArtifactVersion,
    CapabilityRequestRecord,
    CapabilityRequestStatus,
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
    ToolCall,
    ToolCallStatus,
)
from agent_platform.domain.model_runtime import AgentRunStatus, ModelCallStatus
from agent_platform.domain.shared.errors import DomainError, ErrorCategory
from agent_platform.domain.shared.ids import new_id
from agent_platform.domain.workflows import RoomStatus, TaskStatus, WorkflowStatus
from agent_platform.infrastructure.database.models import (
    AgentRunRow,
    ApprovalRow,
    ArtifactRow,
    ArtifactVersionRow,
    CapabilityRequestRow,
    ChangeRequestRow,
    HandoffPacketRow,
    ModelCallRow,
    QualityGateArtifactRow,
    QualityGateIssueRow,
    QualityGateRunRow,
    RecoveryRecordRow,
    RoomRow,
    StageRunRow,
    ToolCallRow,
    WorkflowRow,
    WorkflowTaskRow,
)


class SqlAlchemyGovernanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_capability_request(self, request: CapabilityRequestRecord) -> None:
        self._session.add(_capability_request_row(request))
        await self._session.flush()

    async def get_capability_request(self, request_id: str) -> CapabilityRequestRecord | None:
        row = await self._session.get(CapabilityRequestRow, request_id)
        return _capability_request_from_row(row) if row is not None else None

    async def get_capability_request_by_key(
        self, task_id: str, idempotency_key: str
    ) -> CapabilityRequestRecord | None:
        row = await self._session.scalar(
            select(CapabilityRequestRow).where(
                CapabilityRequestRow.task_id == task_id,
                CapabilityRequestRow.idempotency_key == idempotency_key,
            )
        )
        return _capability_request_from_row(row) if row is not None else None

    async def list_capability_requests(
        self,
        workflow_id: str,
        *,
        status: CapabilityRequestStatus | None = None,
    ) -> tuple[CapabilityRequestRecord, ...]:
        statement = select(CapabilityRequestRow).where(
            CapabilityRequestRow.workflow_id == workflow_id
        )
        if status is not None:
            statement = statement.where(CapabilityRequestRow.status == status.value)
        rows = (
            await self._session.scalars(
                statement.order_by(CapabilityRequestRow.requested_at, CapabilityRequestRow.id)
            )
        ).all()
        return tuple(_capability_request_from_row(row) for row in rows)

    async def find_approved_capability(
        self,
        task_id: str,
        capability: str,
    ) -> CapabilityRequestRecord | None:
        row = await self._session.scalar(
            select(CapabilityRequestRow)
            .where(
                CapabilityRequestRow.task_id == task_id,
                CapabilityRequestRow.capability == capability,
                CapabilityRequestRow.status == CapabilityRequestStatus.APPROVED.value,
            )
            .order_by(CapabilityRequestRow.decided_at.desc(), CapabilityRequestRow.id.desc())
            .limit(1)
        )
        return _capability_request_from_row(row) if row is not None else None

    async def decide_capability_request(
        self,
        request_id: str,
        status: CapabilityRequestStatus,
        *,
        expected_version: int,
        decided_at: datetime,
        reason: str | None,
    ) -> CapabilityRequestRecord:
        row = await self._require_capability_request_row(request_id)
        _require_version("capability_request", row.version, expected_version)
        if CapabilityRequestStatus(row.status) is not CapabilityRequestStatus.PENDING:
            raise _conflict("capability_request.already_decided", "Capability request is decided")
        if status not in {CapabilityRequestStatus.APPROVED, CapabilityRequestStatus.REJECTED}:
            raise ValueError("capability decision status is invalid")
        row.status = status.value
        row.version += 1
        row.decided_at = decided_at
        row.decision_reason = reason
        await self._session.flush()
        return _capability_request_from_row(row)

    async def expire_capabilities_for_task(self, task_id: str, *, decided_at: datetime) -> int:
        rows = (
            await self._session.scalars(
                select(CapabilityRequestRow).where(
                    CapabilityRequestRow.task_id == task_id,
                    CapabilityRequestRow.status.in_(
                        (
                            CapabilityRequestStatus.PENDING.value,
                            CapabilityRequestStatus.APPROVED.value,
                        )
                    ),
                )
            )
        ).all()
        for row in rows:
            row.status = CapabilityRequestStatus.EXPIRED.value
            row.version += 1
            row.decided_at = decided_at
            row.decision_reason = "task_terminal"
        await self._session.flush()
        return len(rows)

    async def add_approval(self, approval: Approval) -> None:
        self._session.add(_approval_row(approval))
        await self._session.flush()

    async def get_approval(self, approval_id: str) -> Approval | None:
        row = await self._session.get(ApprovalRow, approval_id)
        return _approval_from_row(row) if row is not None else None

    async def get_approval_for_target(self, kind: ApprovalKind, target_id: str) -> Approval | None:
        row = await self._session.scalar(
            select(ApprovalRow).where(
                ApprovalRow.kind == kind.value,
                ApprovalRow.target_id == target_id,
            )
        )
        return _approval_from_row(row) if row is not None else None

    async def list_approvals(
        self, workflow_id: str, *, status: ApprovalStatus | None = None
    ) -> tuple[Approval, ...]:
        statement = select(ApprovalRow).where(ApprovalRow.workflow_id == workflow_id)
        if status is not None:
            statement = statement.where(ApprovalRow.status == status.value)
        rows = (
            await self._session.scalars(
                statement.order_by(ApprovalRow.requested_at, ApprovalRow.id)
            )
        ).all()
        return tuple(_approval_from_row(row) for row in rows)

    async def decide_approval(
        self,
        approval_id: str,
        status: ApprovalStatus,
        *,
        expected_version: int,
        decided_at: datetime,
        reason: str | None,
    ) -> Approval:
        row = await self._require_approval_row(approval_id)
        _require_version("approval", row.version, expected_version)
        if ApprovalStatus(row.status) is not ApprovalStatus.PENDING:
            raise _conflict("approval.already_decided", "Approval is already decided")
        if status not in {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED}:
            raise ValueError("approval decision status is invalid")
        row.status = status.value
        row.version += 1
        row.decided_at = decided_at
        row.reason = reason
        await self._session.flush()
        return _approval_from_row(row)

    async def add_tool_call(self, call: ToolCall) -> None:
        self._session.add(_tool_call_row(call))
        await self._session.flush()

    async def get_tool_call(self, call_id: str) -> ToolCall | None:
        row = await self._session.get(ToolCallRow, call_id)
        return _tool_call_from_row(row) if row is not None else None

    async def get_tool_call_by_key(self, task_id: str, idempotency_key: str) -> ToolCall | None:
        row = await self._session.scalar(
            select(ToolCallRow).where(
                ToolCallRow.task_id == task_id,
                ToolCallRow.idempotency_key == idempotency_key,
            )
        )
        return _tool_call_from_row(row) if row is not None else None

    async def list_tool_calls(self, workflow_id: str) -> tuple[ToolCall, ...]:
        rows = (
            await self._session.scalars(
                select(ToolCallRow)
                .where(ToolCallRow.workflow_id == workflow_id)
                .order_by(ToolCallRow.started_at, ToolCallRow.id)
            )
        ).all()
        return tuple(_tool_call_from_row(row) for row in rows)

    async def finish_tool_call(
        self,
        call_id: str,
        status: ToolCallStatus,
        *,
        completed_at: datetime,
        result: dict[str, object],
        error_code: str | None,
    ) -> ToolCall:
        row = await self._require_tool_call_row(call_id)
        if ToolCallStatus(row.status) is not ToolCallStatus.RUNNING:
            return _tool_call_from_row(row)
        row.status = status.value
        row.completed_at = completed_at
        row.result = deepcopy(result)
        row.error_code = error_code
        await self._session.flush()
        return _tool_call_from_row(row)

    async def add_artifact(self, artifact: Artifact) -> None:
        self._session.add(_artifact_row(artifact))
        await self._session.flush()

    async def get_artifact(self, artifact_id: str) -> Artifact | None:
        row = await self._session.get(ArtifactRow, artifact_id)
        return _artifact_from_row(row) if row is not None else None

    async def find_artifact(self, workflow_id: str, stage: Stage, name: str) -> Artifact | None:
        row = await self._session.scalar(
            select(ArtifactRow).where(
                ArtifactRow.workflow_id == workflow_id,
                ArtifactRow.stage == stage.value,
                ArtifactRow.name == name,
            )
        )
        return _artifact_from_row(row) if row is not None else None

    async def list_artifacts(self, workflow_id: str) -> tuple[Artifact, ...]:
        rows = (
            await self._session.scalars(
                select(ArtifactRow)
                .where(ArtifactRow.workflow_id == workflow_id)
                .order_by(ArtifactRow.stage, ArtifactRow.name, ArtifactRow.id)
            )
        ).all()
        return tuple(_artifact_from_row(row) for row in rows)

    async def add_artifact_version(self, version: ArtifactVersion) -> None:
        previous = await self.latest_artifact_version(version.artifact_id)
        if previous is not None:
            row = await self._require_artifact_version_row(previous.id)
            if ArtifactStatus(row.status) is not ArtifactStatus.INVALIDATED:
                row.status = ArtifactStatus.SUPERSEDED.value
        self._session.add(_artifact_version_row(version))
        await self._session.flush()

    async def get_artifact_version(self, version_id: str) -> ArtifactVersion | None:
        row = await self._session.get(ArtifactVersionRow, version_id)
        return _artifact_version_from_row(row) if row is not None else None

    async def latest_artifact_version(self, artifact_id: str) -> ArtifactVersion | None:
        row = await self._session.scalar(
            select(ArtifactVersionRow)
            .where(ArtifactVersionRow.artifact_id == artifact_id)
            .order_by(ArtifactVersionRow.version.desc(), ArtifactVersionRow.id.desc())
            .limit(1)
        )
        return _artifact_version_from_row(row) if row is not None else None

    async def list_artifact_versions(self, workflow_id: str) -> tuple[ArtifactVersion, ...]:
        rows = (
            await self._session.scalars(
                select(ArtifactVersionRow)
                .join(ArtifactRow, ArtifactRow.id == ArtifactVersionRow.artifact_id)
                .where(ArtifactRow.workflow_id == workflow_id)
                .order_by(ArtifactRow.stage, ArtifactRow.name, ArtifactVersionRow.version)
            )
        ).all()
        return tuple(_artifact_version_from_row(row) for row in rows)

    async def lock_artifact_versions(
        self,
        version_ids: tuple[str, ...],
        *,
        checkpoint_id: str,
        locked_at: datetime,
    ) -> tuple[ArtifactVersion, ...]:
        versions: list[ArtifactVersion] = []
        for version_id in version_ids:
            row = await self._require_artifact_version_row(version_id)
            if ArtifactStatus(row.status) is not ArtifactStatus.DRAFT:
                raise _conflict("artifact.not_lockable", "Artifact version is not a draft")
            row.status = ArtifactStatus.LOCKED.value
            row.checkpoint_id = checkpoint_id
            row.locked_at = locked_at
            versions.append(_artifact_version_from_row(row))
        await self._session.flush()
        return tuple(versions)

    async def invalidate_artifacts_from_stage(
        self,
        workflow_id: str,
        stages: tuple[Stage, ...],
        *,
        invalidated_at: datetime,
        reason: str,
    ) -> int:
        rows = (
            await self._session.scalars(
                select(ArtifactVersionRow)
                .join(ArtifactRow, ArtifactRow.id == ArtifactVersionRow.artifact_id)
                .where(
                    ArtifactRow.workflow_id == workflow_id,
                    ArtifactRow.stage.in_(tuple(stage.value for stage in stages)),
                    ArtifactVersionRow.status.in_(
                        (ArtifactStatus.DRAFT.value, ArtifactStatus.LOCKED.value)
                    ),
                )
            )
        ).all()
        for row in rows:
            row.status = ArtifactStatus.INVALIDATED.value
            row.invalidated_at = invalidated_at
            row.invalidation_reason = reason
        await self._session.flush()
        return len(rows)

    async def add_gate(self, gate: QualityGateRun) -> None:
        self._session.add(_gate_row(gate))
        await self._session.flush()
        for issue in gate.issues:
            self._session.add(
                QualityGateIssueRow(
                    id=new_id("issue"),
                    gate_run_id=gate.id,
                    code=issue.code,
                    severity=issue.severity.value,
                    message=issue.message,
                    details=deepcopy(issue.details),
                )
            )
        for version_id in gate.artifact_version_ids:
            self._session.add(
                QualityGateArtifactRow(
                    gate_run_id=gate.id,
                    artifact_version_id=version_id,
                )
            )
        await self._session.flush()

    async def get_gate(self, gate_id: str) -> QualityGateRun | None:
        row = await self._session.get(QualityGateRunRow, gate_id)
        return await self._gate_from_row(row) if row is not None else None

    async def list_gates(self, workflow_id: str) -> tuple[QualityGateRun, ...]:
        rows = (
            await self._session.scalars(
                select(QualityGateRunRow)
                .where(QualityGateRunRow.workflow_id == workflow_id)
                .order_by(QualityGateRunRow.evaluated_at, QualityGateRunRow.id)
            )
        ).all()
        return tuple([await self._gate_from_row(row) for row in rows])

    async def resolve_gate(
        self,
        gate_id: str,
        resolution: GateResolution,
        *,
        expected_version: int,
        resolved_at: datetime,
    ) -> QualityGateRun:
        row = await self._require_gate_row(gate_id)
        _require_version("quality_gate", row.version, expected_version)
        if GateResolution(row.resolution) is not GateResolution.PENDING:
            raise _conflict("quality_gate.already_resolved", "Quality gate is already resolved")
        row.resolution = resolution.value
        row.version += 1
        row.resolved_at = resolved_at
        await self._session.flush()
        return await self._gate_from_row(row)

    async def add_handoff(self, handoff: HandoffPacket) -> None:
        self._session.add(_handoff_row(handoff))
        await self._session.flush()

    async def list_handoffs(self, workflow_id: str) -> tuple[HandoffPacket, ...]:
        rows = (
            await self._session.scalars(
                select(HandoffPacketRow)
                .where(HandoffPacketRow.workflow_id == workflow_id)
                .order_by(HandoffPacketRow.created_at, HandoffPacketRow.id)
            )
        ).all()
        return tuple(_handoff_from_row(row) for row in rows)

    async def invalidate_handoffs_from_stage(
        self,
        workflow_id: str,
        stages: tuple[Stage, ...],
        *,
        invalidated_at: datetime,
        reason: str,
    ) -> int:
        rows = (
            await self._session.scalars(
                select(HandoffPacketRow).where(
                    HandoffPacketRow.workflow_id == workflow_id,
                    HandoffPacketRow.from_stage.in_(tuple(stage.value for stage in stages)),
                    HandoffPacketRow.status == HandoffStatus.ACTIVE.value,
                )
            )
        ).all()
        for row in rows:
            row.status = HandoffStatus.INVALIDATED.value
            row.invalidated_at = invalidated_at
            row.invalidation_reason = reason
        await self._session.flush()
        return len(rows)

    async def add_change_request(self, request: ChangeRequest) -> None:
        self._session.add(_change_request_row(request))
        await self._session.flush()

    async def list_change_requests(self, workflow_id: str) -> tuple[ChangeRequest, ...]:
        rows = (
            await self._session.scalars(
                select(ChangeRequestRow)
                .where(ChangeRequestRow.workflow_id == workflow_id)
                .order_by(ChangeRequestRow.created_at, ChangeRequestRow.id)
            )
        ).all()
        return tuple(_change_request_from_row(row) for row in rows)

    async def add_recovery(self, recovery: RecoveryRecord) -> None:
        self._session.add(_recovery_row(recovery))
        await self._session.flush()

    async def list_recoveries(
        self, *, status: RecoveryStatus | None = None
    ) -> tuple[RecoveryRecord, ...]:
        statement = select(RecoveryRecordRow)
        if status is not None:
            statement = statement.where(RecoveryRecordRow.status == status.value)
        rows = (
            await self._session.scalars(
                statement.order_by(RecoveryRecordRow.detected_at, RecoveryRecordRow.id)
            )
        ).all()
        return tuple(_recovery_from_row(row) for row in rows)

    async def get_recovery(self, recovery_id: str) -> RecoveryRecord | None:
        row = await self._session.get(RecoveryRecordRow, recovery_id)
        return _recovery_from_row(row) if row is not None else None

    async def resolve_recovery(
        self, recovery_id: str, status: RecoveryStatus, *, resolved_at: datetime
    ) -> RecoveryRecord:
        row = await self._session.get(RecoveryRecordRow, recovery_id)
        if row is None:
            raise _not_found("recovery", "Recovery record was not found")
        if RecoveryStatus(row.status) is not RecoveryStatus.PENDING:
            raise _conflict("recovery.already_resolved", "Recovery record is already resolved")
        if status not in {RecoveryStatus.RESUMED, RecoveryStatus.DISCARDED}:
            raise ValueError("recovery resolution is invalid")
        row.status = status.value
        row.resolved_at = resolved_at
        await self._session.flush()
        return _recovery_from_row(row)

    async def set_workflow_mode(
        self,
        workflow_id: str,
        mode: ExecutionMode,
        *,
        expected_version: int,
        updated_at: datetime,
    ) -> None:
        row = await self._require_workflow_row(workflow_id)
        _require_version("workflow", row.version, expected_version)
        if WorkflowStatus(row.status) in {
            WorkflowStatus.COMPLETED,
            WorkflowStatus.STOPPED,
            WorkflowStatus.ABANDONED,
            WorkflowStatus.FAILED,
        }:
            raise _conflict("workflow.terminal", "Terminal workflow mode cannot change")
        row.execution_mode = mode.value
        row.version += 1
        row.updated_at = updated_at
        await self._session.flush()

    async def set_workflow_status(
        self,
        workflow_id: str,
        status: WorkflowStatus,
        *,
        updated_at: datetime,
    ) -> None:
        row = await self._require_workflow_row(workflow_id)
        row.status = status.value
        row.version += 1
        row.updated_at = updated_at
        await self._session.flush()

    async def set_stage_state(
        self,
        stage_run_id: str,
        state: StageRunState,
        *,
        updated_at: datetime,
    ) -> None:
        row = await self._session.get(StageRunRow, stage_run_id)
        if row is None:
            raise _not_found("stage_run", "Stage run was not found")
        row.state = state.value
        row.version += 1
        if state is StageRunState.COMPLETED:
            row.completed_at = updated_at
        await self._session.flush()

    async def cancel_tasks(
        self,
        workflow_id: str,
        *,
        completed_at: datetime,
        include_queued: bool = True,
    ) -> int:
        statuses = (
            (TaskStatus.QUEUED.value, TaskStatus.RUNNING.value)
            if include_queued
            else (TaskStatus.RUNNING.value,)
        )
        rows = (
            await self._session.scalars(
                select(WorkflowTaskRow).where(
                    WorkflowTaskRow.workflow_id == workflow_id,
                    WorkflowTaskRow.status.in_(statuses),
                )
            )
        ).all()
        for row in rows:
            row.status = TaskStatus.CANCELLED.value
            row.version += 1
            row.completed_at = completed_at
        await self._session.flush()
        return len(rows)

    async def active_agent_run_ids(self, workflow_id: str) -> tuple[str, ...]:
        return tuple(
            (
                await self._session.scalars(
                    select(AgentRunRow.id).where(
                        AgentRunRow.workflow_id == workflow_id,
                        AgentRunRow.status.in_(
                            (AgentRunStatus.PENDING.value, AgentRunStatus.RUNNING.value)
                        ),
                    )
                )
            ).all()
        )

    async def cancel_agent_runs(self, workflow_id: str, *, completed_at: datetime) -> int:
        rows = (
            await self._session.scalars(
                select(AgentRunRow).where(
                    AgentRunRow.workflow_id == workflow_id,
                    AgentRunRow.status.in_(
                        (AgentRunStatus.PENDING.value, AgentRunStatus.RUNNING.value)
                    ),
                )
            )
        ).all()
        for row in rows:
            row.status = AgentRunStatus.CANCELLED.value
            row.version += 1
            row.completed_at = completed_at
            row.error_code = "agent_run.cancelled_by_workflow"
            call_rows = (
                await self._session.scalars(
                    select(ModelCallRow).where(
                        ModelCallRow.agent_run_id == row.id,
                        ModelCallRow.status.in_(
                            (ModelCallStatus.PENDING.value, ModelCallStatus.STREAMING.value)
                        ),
                    )
                )
            ).all()
            for call in call_rows:
                call.status = ModelCallStatus.CANCELLED.value
                call.version += 1
                call.completed_at = completed_at
                call.error_code = "model.call_cancelled_by_workflow"
        await self._session.flush()
        return len(rows)

    async def cancel_tool_calls(self, workflow_id: str, *, completed_at: datetime) -> int:
        rows = (
            await self._session.scalars(
                select(ToolCallRow).where(
                    ToolCallRow.workflow_id == workflow_id,
                    ToolCallRow.status == ToolCallStatus.RUNNING.value,
                )
            )
        ).all()
        for row in rows:
            row.status = ToolCallStatus.CANCELLED.value
            row.completed_at = completed_at
            row.error_code = "tool.cancelled_by_workflow"
        await self._session.flush()
        return len(rows)

    async def archive_stage_room(self, stage_run_id: str, *, updated_at: datetime) -> None:
        row = await self._session.scalar(
            select(RoomRow).where(RoomRow.stage_run_id == stage_run_id)
        )
        if row is None:
            raise _not_found("room", "Stage room was not found")
        row.status = RoomStatus.ARCHIVED.value
        row.version += 1
        row.updated_at = updated_at
        await self._session.flush()

    async def recover_incomplete(self, *, detected_at: datetime) -> tuple[RecoveryRecord, ...]:
        workflow_rows = (
            await self._session.scalars(
                select(WorkflowRow).where(
                    WorkflowRow.status.in_(
                        (
                            WorkflowStatus.RUNNING.value,
                            WorkflowStatus.WAITING_USER.value,
                            WorkflowStatus.WARNING_BLOCKED.value,
                        )
                    )
                )
            )
        ).all()
        recoveries: list[RecoveryRecord] = []
        for workflow in workflow_rows:
            task_rows = (
                await self._session.scalars(
                    select(WorkflowTaskRow).where(
                        WorkflowTaskRow.workflow_id == workflow.id,
                        WorkflowTaskRow.status == TaskStatus.RUNNING.value,
                    )
                )
            ).all()
            agent_rows = (
                await self._session.scalars(
                    select(AgentRunRow).where(
                        AgentRunRow.workflow_id == workflow.id,
                        AgentRunRow.status.in_(
                            (AgentRunStatus.PENDING.value, AgentRunStatus.RUNNING.value)
                        ),
                    )
                )
            ).all()
            tool_rows = (
                await self._session.scalars(
                    select(ToolCallRow).where(
                        ToolCallRow.workflow_id == workflow.id,
                        ToolCallRow.status == ToolCallStatus.RUNNING.value,
                    )
                )
            ).all()
            if not task_rows and not agent_rows and not tool_rows:
                continue
            stage_row = await self._session.scalar(
                select(StageRunRow)
                .where(
                    StageRunRow.workflow_id == workflow.id,
                    StageRunRow.stage == workflow.current_stage,
                )
                .order_by(StageRunRow.attempt.desc())
                .limit(1)
            )
            for task in task_rows:
                task.status = TaskStatus.CANCELLED.value
                task.version += 1
                task.completed_at = detected_at
            for run in agent_rows:
                run.status = AgentRunStatus.CANCELLED.value
                run.version += 1
                run.completed_at = detected_at
                run.error_code = "agent_run.interrupted_by_restart"
                call_rows = (
                    await self._session.scalars(
                        select(ModelCallRow).where(
                            ModelCallRow.agent_run_id == run.id,
                            ModelCallRow.status.in_(
                                (
                                    ModelCallStatus.PENDING.value,
                                    ModelCallStatus.STREAMING.value,
                                )
                            ),
                        )
                    )
                ).all()
                for call in call_rows:
                    call.status = ModelCallStatus.CANCELLED.value
                    call.version += 1
                    call.completed_at = detected_at
                    call.error_code = "model.call_interrupted_by_restart"
            for tool_call in tool_rows:
                tool_call.status = ToolCallStatus.INTERRUPTED.value
                tool_call.completed_at = detected_at
                tool_call.error_code = "tool.interrupted_by_restart"
            workflow.status = WorkflowStatus.INTERRUPTED.value
            workflow.version += 1
            workflow.updated_at = detected_at
            if stage_row is not None:
                stage_row.state = StageRunState.INTERRUPTED.value
                stage_row.version += 1
            recovery = RecoveryRecord(
                schema_version=1,
                id=new_id("recovery"),
                project_id=workflow.project_id,
                workflow_id=workflow.id,
                stage_run_id=stage_row.id if stage_row is not None else None,
                status=RecoveryStatus.PENDING,
                interrupted_tasks=len(task_rows),
                interrupted_agent_runs=len(agent_rows),
                interrupted_tool_calls=len(tool_rows),
                detected_at=detected_at,
            )
            self._session.add(_recovery_row(recovery))
            recoveries.append(recovery)
        await self._session.flush()
        return tuple(recoveries)

    async def _gate_from_row(self, row: QualityGateRunRow) -> QualityGateRun:
        issue_rows = (
            await self._session.scalars(
                select(QualityGateIssueRow)
                .where(QualityGateIssueRow.gate_run_id == row.id)
                .order_by(QualityGateIssueRow.code)
            )
        ).all()
        version_ids = tuple(
            (
                await self._session.scalars(
                    select(QualityGateArtifactRow.artifact_version_id)
                    .where(QualityGateArtifactRow.gate_run_id == row.id)
                    .order_by(QualityGateArtifactRow.artifact_version_id)
                )
            ).all()
        )
        return QualityGateRun(
            schema_version=1,
            id=row.id,
            project_id=row.project_id,
            workflow_id=row.workflow_id,
            stage_run_id=row.stage_run_id,
            status=GateStatus(row.status),
            resolution=GateResolution(row.resolution),
            issues=tuple(
                GateIssue(
                    code=issue.code,
                    severity=GateIssueSeverity(issue.severity),
                    message=issue.message,
                    details=deepcopy(issue.details),
                )
                for issue in issue_rows
            ),
            artifact_version_ids=version_ids,
            version=row.version,
            evaluated_at=row.evaluated_at,
            resolved_at=row.resolved_at,
        )

    async def _require_capability_request_row(self, request_id: str) -> CapabilityRequestRow:
        row = await self._session.get(CapabilityRequestRow, request_id)
        if row is None:
            raise _not_found("capability_request", "Capability request was not found")
        return row

    async def _require_approval_row(self, approval_id: str) -> ApprovalRow:
        row = await self._session.get(ApprovalRow, approval_id)
        if row is None:
            raise _not_found("approval", "Approval was not found")
        return row

    async def _require_tool_call_row(self, call_id: str) -> ToolCallRow:
        row = await self._session.get(ToolCallRow, call_id)
        if row is None:
            raise _not_found("tool_call", "Tool call was not found")
        return row

    async def _require_artifact_version_row(self, version_id: str) -> ArtifactVersionRow:
        row = await self._session.get(ArtifactVersionRow, version_id)
        if row is None:
            raise _not_found("artifact_version", "Artifact version was not found")
        return row

    async def _require_gate_row(self, gate_id: str) -> QualityGateRunRow:
        row = await self._session.get(QualityGateRunRow, gate_id)
        if row is None:
            raise _not_found("quality_gate", "Quality gate was not found")
        return row

    async def _require_workflow_row(self, workflow_id: str) -> WorkflowRow:
        row = await self._session.get(WorkflowRow, workflow_id)
        if row is None:
            raise _not_found("workflow", "Workflow was not found")
        return row


def _capability_request_row(request: CapabilityRequestRecord) -> CapabilityRequestRow:
    return CapabilityRequestRow(
        id=request.id,
        project_id=request.project_id,
        workflow_id=request.workflow_id,
        stage_run_id=request.stage_run_id,
        task_id=request.task_id,
        schema_version=request.schema_version,
        stage=request.stage.value,
        capability=request.capability,
        reason=request.reason,
        target_paths=list(request.target_paths),
        command=list(request.command) if request.command is not None else None,
        status=request.status.value,
        risk_level=request.risk_level,
        idempotency_key=request.idempotency_key,
        version=request.version,
        requested_at=request.requested_at,
        decided_at=request.decided_at,
        decision_reason=request.decision_reason,
    )


def _capability_request_from_row(row: CapabilityRequestRow) -> CapabilityRequestRecord:
    return CapabilityRequestRecord(
        schema_version=1,
        id=row.id,
        project_id=row.project_id,
        workflow_id=row.workflow_id,
        stage_run_id=row.stage_run_id,
        task_id=row.task_id,
        stage=Stage(row.stage),
        capability=row.capability,
        reason=row.reason,
        target_paths=tuple(row.target_paths),
        command=tuple(row.command) if row.command is not None else None,
        status=CapabilityRequestStatus(row.status),
        risk_level=row.risk_level,
        idempotency_key=row.idempotency_key,
        version=row.version,
        requested_at=row.requested_at,
        decided_at=row.decided_at,
        decision_reason=row.decision_reason,
    )


def _approval_row(approval: Approval) -> ApprovalRow:
    return ApprovalRow(
        id=approval.id,
        project_id=approval.project_id,
        workflow_id=approval.workflow_id,
        schema_version=approval.schema_version,
        kind=approval.kind.value,
        target_id=approval.target_id,
        status=approval.status.value,
        version=approval.version,
        requested_at=approval.requested_at,
        decided_at=approval.decided_at,
        reason=approval.reason,
    )


def _approval_from_row(row: ApprovalRow) -> Approval:
    return Approval(
        schema_version=1,
        id=row.id,
        project_id=row.project_id,
        workflow_id=row.workflow_id,
        kind=ApprovalKind(row.kind),
        target_id=row.target_id,
        status=ApprovalStatus(row.status),
        version=row.version,
        requested_at=row.requested_at,
        decided_at=row.decided_at,
        reason=row.reason,
    )


def _tool_call_row(call: ToolCall) -> ToolCallRow:
    return ToolCallRow(
        id=call.id,
        project_id=call.project_id,
        workflow_id=call.workflow_id,
        stage_run_id=call.stage_run_id,
        task_id=call.task_id,
        capability_request_id=call.capability_request_id,
        schema_version=call.schema_version,
        tool_name=call.tool_name,
        capability=call.capability,
        idempotency_key=call.idempotency_key,
        arguments_hash=call.arguments_hash,
        status=call.status.value,
        result=deepcopy(call.result),
        error_code=call.error_code,
        started_at=call.started_at,
        completed_at=call.completed_at,
    )


def _tool_call_from_row(row: ToolCallRow) -> ToolCall:
    return ToolCall(
        schema_version=1,
        id=row.id,
        project_id=row.project_id,
        workflow_id=row.workflow_id,
        stage_run_id=row.stage_run_id,
        task_id=row.task_id,
        capability_request_id=row.capability_request_id,
        tool_name=row.tool_name,
        capability=row.capability,
        idempotency_key=row.idempotency_key,
        arguments_hash=row.arguments_hash,
        status=ToolCallStatus(row.status),
        result=deepcopy(row.result),
        error_code=row.error_code,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


def _artifact_row(artifact: Artifact) -> ArtifactRow:
    return ArtifactRow(
        id=artifact.id,
        project_id=artifact.project_id,
        workflow_id=artifact.workflow_id,
        schema_version=artifact.schema_version,
        stage=artifact.stage.value,
        name=artifact.name,
        relative_path=artifact.relative_path,
        created_at=artifact.created_at,
    )


def _artifact_from_row(row: ArtifactRow) -> Artifact:
    return Artifact(
        schema_version=1,
        id=row.id,
        project_id=row.project_id,
        workflow_id=row.workflow_id,
        stage=Stage(row.stage),
        name=row.name,
        relative_path=row.relative_path,
        created_at=row.created_at,
    )


def _artifact_version_row(version: ArtifactVersion) -> ArtifactVersionRow:
    return ArtifactVersionRow(
        id=version.id,
        artifact_id=version.artifact_id,
        stage_run_id=version.stage_run_id,
        schema_version=version.schema_version,
        version=version.version,
        content_hash=version.content_hash,
        byte_size=version.byte_size,
        status=version.status.value,
        supersedes_id=version.supersedes_id,
        checkpoint_id=version.checkpoint_id,
        created_at=version.created_at,
        locked_at=version.locked_at,
        invalidated_at=version.invalidated_at,
        invalidation_reason=version.invalidation_reason,
    )


def _artifact_version_from_row(row: ArtifactVersionRow) -> ArtifactVersion:
    return ArtifactVersion(
        schema_version=1,
        id=row.id,
        artifact_id=row.artifact_id,
        stage_run_id=row.stage_run_id,
        version=row.version,
        content_hash=row.content_hash,
        byte_size=row.byte_size,
        status=ArtifactStatus(row.status),
        supersedes_id=row.supersedes_id,
        checkpoint_id=row.checkpoint_id,
        created_at=row.created_at,
        locked_at=row.locked_at,
        invalidated_at=row.invalidated_at,
        invalidation_reason=row.invalidation_reason,
    )


def _gate_row(gate: QualityGateRun) -> QualityGateRunRow:
    return QualityGateRunRow(
        id=gate.id,
        project_id=gate.project_id,
        workflow_id=gate.workflow_id,
        stage_run_id=gate.stage_run_id,
        schema_version=gate.schema_version,
        status=gate.status.value,
        resolution=gate.resolution.value,
        version=gate.version,
        evaluated_at=gate.evaluated_at,
        resolved_at=gate.resolved_at,
    )


def _handoff_row(handoff: HandoffPacket) -> HandoffPacketRow:
    return HandoffPacketRow(
        id=handoff.id,
        project_id=handoff.project_id,
        workflow_id=handoff.workflow_id,
        from_stage_run_id=handoff.from_stage_run_id,
        schema_version=handoff.schema_version,
        from_stage=handoff.from_stage.value,
        to_stage=handoff.to_stage.value if handoff.to_stage is not None else None,
        gate_run_id=handoff.gate_run_id,
        checkpoint_id=handoff.checkpoint_id,
        artifact_version_ids=list(handoff.artifact_version_ids),
        content_hash=handoff.content_hash,
        status=handoff.status.value,
        created_at=handoff.created_at,
        invalidated_at=handoff.invalidated_at,
        invalidation_reason=handoff.invalidation_reason,
    )


def _handoff_from_row(row: HandoffPacketRow) -> HandoffPacket:
    return HandoffPacket(
        schema_version=1,
        id=row.id,
        project_id=row.project_id,
        workflow_id=row.workflow_id,
        from_stage_run_id=row.from_stage_run_id,
        from_stage=Stage(row.from_stage),
        to_stage=Stage(row.to_stage) if row.to_stage is not None else None,
        gate_run_id=row.gate_run_id,
        checkpoint_id=row.checkpoint_id,
        artifact_version_ids=tuple(row.artifact_version_ids),
        content_hash=row.content_hash,
        status=HandoffStatus(row.status),
        created_at=row.created_at,
        invalidated_at=row.invalidated_at,
        invalidation_reason=row.invalidation_reason,
    )


def _change_request_row(request: ChangeRequest) -> ChangeRequestRow:
    return ChangeRequestRow(
        id=request.id,
        project_id=request.project_id,
        workflow_id=request.workflow_id,
        source_stage_run_id=request.source_stage_run_id,
        schema_version=request.schema_version,
        target_stage=request.target_stage.value,
        gate_run_id=request.gate_run_id,
        reason=request.reason,
        status=request.status.value,
        input_artifact_version_ids=list(request.input_artifact_version_ids),
        created_at=request.created_at,
        resolved_at=request.resolved_at,
    )


def _change_request_from_row(row: ChangeRequestRow) -> ChangeRequest:
    return ChangeRequest(
        schema_version=1,
        id=row.id,
        project_id=row.project_id,
        workflow_id=row.workflow_id,
        source_stage_run_id=row.source_stage_run_id,
        target_stage=Stage(row.target_stage),
        gate_run_id=row.gate_run_id,
        reason=row.reason,
        status=ChangeRequestStatus(row.status),
        input_artifact_version_ids=tuple(row.input_artifact_version_ids),
        created_at=row.created_at,
        resolved_at=row.resolved_at,
    )


def _recovery_row(recovery: RecoveryRecord) -> RecoveryRecordRow:
    return RecoveryRecordRow(
        id=recovery.id,
        project_id=recovery.project_id,
        workflow_id=recovery.workflow_id,
        stage_run_id=recovery.stage_run_id,
        schema_version=recovery.schema_version,
        status=recovery.status.value,
        interrupted_tasks=recovery.interrupted_tasks,
        interrupted_agent_runs=recovery.interrupted_agent_runs,
        interrupted_tool_calls=recovery.interrupted_tool_calls,
        detected_at=recovery.detected_at,
        resolved_at=recovery.resolved_at,
    )


def _recovery_from_row(row: RecoveryRecordRow) -> RecoveryRecord:
    return RecoveryRecord(
        schema_version=1,
        id=row.id,
        project_id=row.project_id,
        workflow_id=row.workflow_id,
        stage_run_id=row.stage_run_id,
        status=RecoveryStatus(row.status),
        interrupted_tasks=row.interrupted_tasks,
        interrupted_agent_runs=row.interrupted_agent_runs,
        interrupted_tool_calls=row.interrupted_tool_calls,
        detected_at=row.detected_at,
        resolved_at=row.resolved_at,
    )


def _require_version(entity: str, current: int, expected: int) -> None:
    if current != expected:
        raise DomainError(
            code=f"{entity}.version_conflict",
            message=f"{entity.replace('_', ' ').title()} version has changed",
            details={"current_version": current},
            category=ErrorCategory.CONFLICT,
        )


def _not_found(entity: str, message: str) -> DomainError:
    return DomainError(
        code=f"{entity}.not_found",
        message=message,
        category=ErrorCategory.NOT_FOUND,
    )


def _conflict(code: str, message: str) -> DomainError:
    return DomainError(code=code, message=message, category=ErrorCategory.CONFLICT)
