from __future__ import annotations

from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Query, Request
from fastapi import Path as ApiPath
from pydantic import BaseModel, ConfigDict, Field

from agent_platform.application.governance import (
    ApprovalDecisionExecution,
    ArtifactInventory,
    GateEvaluation,
    GovernanceApplicationService,
)
from agent_platform.application.tooling import ToolApplicationService, ToolExecution
from agent_platform.domain.contracts import CapabilityRisk, Stage
from agent_platform.domain.governance import (
    Approval,
    ApprovalStatus,
    Artifact,
    ArtifactVersion,
    CapabilityRequestRecord,
    CapabilityRequestStatus,
    ChangeRequest,
    ExecutionMode,
    HandoffPacket,
    QualityGateRun,
    RecoveryRecord,
    ToolCall,
)
from agent_platform.domain.tooling import ToolDefinition
from agent_platform.domain.workflows import Workflow

router = APIRouter(tags=["stage5"])

CorrelationId = Annotated[str, Field(min_length=1, max_length=120)]
WorkflowId = Annotated[str, ApiPath(pattern=r"^workflow_[a-z0-9]+$")]
StageRunId = Annotated[str, ApiPath(pattern=r"^stagerun_[a-z0-9]+$")]
TaskId = Annotated[str, ApiPath(pattern=r"^task_[a-z0-9]+$")]
CapabilityRequestId = Annotated[str, ApiPath(pattern=r"^capreq_[a-z0-9]+$")]
ToolCallId = Annotated[str, ApiPath(pattern=r"^toolcall_[a-z0-9]+$")]
ApprovalId = Annotated[str, ApiPath(pattern=r"^approval_[a-z0-9]+$")]
RecoveryId = Annotated[str, ApiPath(pattern=r"^recovery_[a-z0-9]+$")]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class CatalogResponse(ApiModel):
    tools: tuple[ToolDefinition, ...]


class CapabilityRequestCreate(ApiModel):
    capability: str = Field(pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
    reason: str = Field(min_length=1, max_length=2000)
    target_paths: tuple[str, ...] = ()
    command: tuple[str, ...] | None = None
    risk_level: CapabilityRisk
    idempotency_key: str = Field(min_length=16, max_length=128)
    correlation_id: CorrelationId


class CapabilityRequestList(ApiModel):
    requests: tuple[CapabilityRequestRecord, ...]


class DecisionRequest(ApiModel):
    approved: bool
    expected_version: int = Field(gt=0)
    reason: str | None = Field(default=None, max_length=4000)
    correlation_id: CorrelationId


class ToolExecuteRequest(ApiModel):
    tool_name: str = Field(pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
    idempotency_key: str = Field(min_length=16, max_length=128)
    arguments: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=900, ge=1, le=3600)
    correlation_id: CorrelationId


class ToolExecutionResponse(ApiModel):
    call: ToolCall
    output: dict[str, Any]


class ToolCallList(ApiModel):
    calls: tuple[ToolCall, ...]


class CorrelationRequest(ApiModel):
    correlation_id: CorrelationId


class ModeRequest(ApiModel):
    mode: ExecutionMode
    expected_version: int = Field(gt=0)
    correlation_id: CorrelationId


class ArtifactVersionCreate(ApiModel):
    name: str = Field(min_length=1, max_length=160)
    relative_path: str = Field(min_length=1, max_length=32_767)
    correlation_id: CorrelationId


class ArtifactVersionCreateResponse(ApiModel):
    artifact: Artifact
    version: ArtifactVersion


class ArtifactInventoryResponse(ApiModel):
    artifacts: tuple[Artifact, ...]
    versions: tuple[ArtifactVersion, ...]


class GateEvaluateRequest(ApiModel):
    artifact_version_ids: tuple[str, ...] = Field(min_length=1)
    correlation_id: CorrelationId


class GateEvaluationResponse(ApiModel):
    gate: QualityGateRun
    approval: Approval | None
    handoff: HandoffPacket | None
    change_request: ChangeRequest | None


class GateListResponse(ApiModel):
    gates: tuple[QualityGateRun, ...]


class ApprovalListResponse(ApiModel):
    approvals: tuple[Approval, ...]


class ApprovalDecisionResponse(ApiModel):
    approval: Approval
    gate: QualityGateRun
    handoff: HandoffPacket | None
    change_request: ChangeRequest | None


class HandoffListResponse(ApiModel):
    handoffs: tuple[HandoffPacket, ...]


class ChangeRequestCreate(ApiModel):
    target_stage: Stage
    reason: str = Field(min_length=1, max_length=4000)
    input_artifact_version_ids: tuple[str, ...] = ()
    correlation_id: CorrelationId


class ChangeRequestListResponse(ApiModel):
    change_requests: tuple[ChangeRequest, ...]


class WorkflowControlRequest(ApiModel):
    expected_version: int = Field(gt=0)
    correlation_id: CorrelationId


class RecoveryListResponse(ApiModel):
    recoveries: tuple[RecoveryRecord, ...]


@router.get("/tools/catalog", response_model=CatalogResponse)
async def list_tool_catalog(request: Request) -> CatalogResponse:
    return CatalogResponse(tools=_tool_service(request).list_catalog())


@router.post(
    "/tasks/{task_id}/capability-requests",
    response_model=CapabilityRequestRecord,
    status_code=201,
)
async def request_capability(
    task_id: TaskId,
    payload: CapabilityRequestCreate,
    request: Request,
) -> CapabilityRequestRecord:
    return await _tool_service(request).request_capability(
        task_id,
        capability=payload.capability,
        reason=payload.reason,
        target_paths=payload.target_paths,
        command=payload.command,
        risk_level=payload.risk_level,
        idempotency_key=payload.idempotency_key,
        correlation_id=payload.correlation_id,
    )


@router.get(
    "/workflows/{workflow_id}/capability-requests",
    response_model=CapabilityRequestList,
)
async def list_capability_requests(
    workflow_id: WorkflowId,
    request: Request,
    status: Annotated[CapabilityRequestStatus | None, Query()] = None,
) -> CapabilityRequestList:
    records = await _tool_service(request).list_capability_requests(workflow_id, status=status)
    return CapabilityRequestList(requests=records)


@router.post(
    "/capability-requests/{request_id}/decision",
    response_model=CapabilityRequestRecord,
)
async def decide_capability(
    request_id: CapabilityRequestId,
    payload: DecisionRequest,
    request: Request,
) -> CapabilityRequestRecord:
    return await _tool_service(request).decide_capability(
        request_id,
        approved=payload.approved,
        expected_version=payload.expected_version,
        reason=payload.reason,
        correlation_id=payload.correlation_id,
    )


@router.post("/tasks/{task_id}/tool-calls", response_model=ToolExecutionResponse)
async def execute_tool(
    task_id: TaskId,
    payload: ToolExecuteRequest,
    request: Request,
) -> ToolExecutionResponse:
    execution: ToolExecution = await _tool_service(request).execute(
        task_id,
        tool_name=payload.tool_name,
        idempotency_key=payload.idempotency_key,
        arguments=payload.arguments,
        timeout_seconds=payload.timeout_seconds,
        correlation_id=payload.correlation_id,
    )
    return ToolExecutionResponse(call=execution.call, output=execution.output)


@router.get("/workflows/{workflow_id}/tool-calls", response_model=ToolCallList)
async def list_tool_calls(workflow_id: WorkflowId, request: Request) -> ToolCallList:
    return ToolCallList(calls=await _tool_service(request).list_tool_calls(workflow_id))


@router.post("/tool-calls/{call_id}/cancel", response_model=ToolCall)
async def cancel_tool_call(
    call_id: ToolCallId,
    payload: CorrelationRequest,
    request: Request,
) -> ToolCall:
    return await _tool_service(request).cancel_call(call_id, correlation_id=payload.correlation_id)


@router.post("/workflows/{workflow_id}/mode", response_model=Workflow)
async def set_workflow_mode(
    workflow_id: WorkflowId,
    payload: ModeRequest,
    request: Request,
) -> Workflow:
    return await _governance_service(request).set_execution_mode(
        workflow_id,
        payload.mode,
        expected_version=payload.expected_version,
        correlation_id=payload.correlation_id,
    )


@router.post(
    "/stage-runs/{stage_run_id}/artifact-versions",
    response_model=ArtifactVersionCreateResponse,
    status_code=201,
)
async def create_artifact_version(
    stage_run_id: StageRunId,
    payload: ArtifactVersionCreate,
    request: Request,
) -> ArtifactVersionCreateResponse:
    artifact, version = await _governance_service(request).create_artifact_version(
        stage_run_id,
        name=payload.name,
        relative_path=payload.relative_path,
        correlation_id=payload.correlation_id,
    )
    return ArtifactVersionCreateResponse(artifact=artifact, version=version)


@router.get("/workflows/{workflow_id}/artifacts", response_model=ArtifactInventoryResponse)
async def list_artifacts(workflow_id: WorkflowId, request: Request) -> ArtifactInventoryResponse:
    inventory: ArtifactInventory = await _governance_service(request).list_artifacts(workflow_id)
    return ArtifactInventoryResponse(
        artifacts=inventory.artifacts,
        versions=inventory.versions,
    )


@router.post(
    "/stage-runs/{stage_run_id}/quality-gates",
    response_model=GateEvaluationResponse,
    status_code=201,
)
async def evaluate_quality_gate(
    stage_run_id: StageRunId,
    payload: GateEvaluateRequest,
    request: Request,
) -> GateEvaluationResponse:
    execution: GateEvaluation = await _governance_service(request).evaluate_gate(
        stage_run_id,
        artifact_version_ids=payload.artifact_version_ids,
        correlation_id=payload.correlation_id,
    )
    return GateEvaluationResponse(
        gate=execution.gate,
        approval=execution.approval,
        handoff=execution.handoff,
        change_request=execution.change_request,
    )


@router.get("/workflows/{workflow_id}/quality-gates", response_model=GateListResponse)
async def list_quality_gates(workflow_id: WorkflowId, request: Request) -> GateListResponse:
    return GateListResponse(gates=await _governance_service(request).list_gates(workflow_id))


@router.get("/workflows/{workflow_id}/approvals", response_model=ApprovalListResponse)
async def list_approvals(
    workflow_id: WorkflowId,
    request: Request,
    status: Annotated[ApprovalStatus | None, Query()] = None,
) -> ApprovalListResponse:
    approvals = await _governance_service(request).list_approvals(workflow_id, status=status)
    return ApprovalListResponse(approvals=approvals)


@router.post("/approvals/{approval_id}/decision", response_model=ApprovalDecisionResponse)
async def decide_gate_approval(
    approval_id: ApprovalId,
    payload: DecisionRequest,
    request: Request,
) -> ApprovalDecisionResponse:
    execution: ApprovalDecisionExecution = await _governance_service(request).decide_gate_approval(
        approval_id,
        approved=payload.approved,
        expected_version=payload.expected_version,
        reason=payload.reason,
        correlation_id=payload.correlation_id,
    )
    return ApprovalDecisionResponse(
        approval=execution.approval,
        gate=execution.gate,
        handoff=execution.handoff,
        change_request=execution.change_request,
    )


@router.get("/workflows/{workflow_id}/handoffs", response_model=HandoffListResponse)
async def list_handoffs(workflow_id: WorkflowId, request: Request) -> HandoffListResponse:
    return HandoffListResponse(
        handoffs=await _governance_service(request).list_handoffs(workflow_id)
    )


@router.post(
    "/workflows/{workflow_id}/change-requests",
    response_model=ChangeRequest,
    status_code=201,
)
async def create_change_request(
    workflow_id: WorkflowId,
    payload: ChangeRequestCreate,
    request: Request,
) -> ChangeRequest:
    return await _governance_service(request).create_change_request(
        workflow_id,
        target_stage=payload.target_stage,
        reason=payload.reason,
        input_artifact_version_ids=payload.input_artifact_version_ids,
        correlation_id=payload.correlation_id,
    )


@router.get(
    "/workflows/{workflow_id}/change-requests",
    response_model=ChangeRequestListResponse,
)
async def list_change_requests(
    workflow_id: WorkflowId, request: Request
) -> ChangeRequestListResponse:
    return ChangeRequestListResponse(
        change_requests=await _governance_service(request).list_change_requests(workflow_id)
    )


@router.post("/workflows/{workflow_id}/{action}", response_model=Workflow)
async def control_workflow(
    workflow_id: WorkflowId,
    action: Literal["pause", "resume", "stop", "abandon"],
    payload: WorkflowControlRequest,
    request: Request,
) -> Workflow:
    return await _governance_service(request).control_workflow(
        workflow_id,
        action,
        expected_version=payload.expected_version,
        correlation_id=payload.correlation_id,
    )


@router.get("/recovery", response_model=RecoveryListResponse)
async def list_recoveries(request: Request) -> RecoveryListResponse:
    return RecoveryListResponse(recoveries=await _governance_service(request).list_recoveries())


@router.post("/recovery/{recovery_id}/{action}", response_model=RecoveryRecord)
async def resolve_recovery(
    recovery_id: RecoveryId,
    action: Literal["resume", "discard"],
    payload: CorrelationRequest,
    request: Request,
) -> RecoveryRecord:
    return await _governance_service(request).resolve_recovery(
        recovery_id,
        resume=action == "resume",
        correlation_id=payload.correlation_id,
    )


def _tool_service(request: Request) -> ToolApplicationService:
    return cast(ToolApplicationService, request.app.state.tool_service)


def _governance_service(request: Request) -> GovernanceApplicationService:
    return cast(GovernanceApplicationService, request.app.state.governance_service)
