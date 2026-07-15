from __future__ import annotations

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Request
from fastapi import Path as ApiPath
from pydantic import BaseModel, ConfigDict, Field

from agent_platform.application.projects.service import ProjectApplicationService
from agent_platform.domain.projects import (
    CheckpointReason,
    CheckpointRestorePlan,
    CheckpointRestoreResult,
    ConflictResolution,
    ExternalChange,
    FileConflict,
    Project,
    ProjectCheckpoint,
    ProjectManifest,
    ProjectPreflightResult,
    ProjectRegistration,
    WorkspaceMode,
)

router = APIRouter(prefix="/projects", tags=["projects"])
CorrelationId = Annotated[str, Field(min_length=1, max_length=120)]
ProjectIdPath = Annotated[str, ApiPath(pattern=r"^project_[a-z0-9]+$")]
CheckpointIdPath = Annotated[str, ApiPath(pattern=r"^checkpoint_[a-z0-9]+$")]
ConflictIdPath = Annotated[str, ApiPath(pattern=r"^conflict_[a-z0-9]+$")]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class ProjectCreateRequest(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    goal: str = Field(min_length=1, max_length=10_000)
    local_working_directory: str = Field(min_length=1, max_length=32_767)
    workspace_mode: WorkspaceMode
    correlation_id: CorrelationId


class ProjectCreateResponse(ApiModel):
    registration: ProjectRegistration
    manifest: ProjectManifest
    preflight_required: Literal[True] = True


class ProjectListResponse(ApiModel):
    projects: tuple[ProjectRegistration, ...]


class ProjectVersionCommand(ApiModel):
    expected_version: int = Field(gt=0)
    correlation_id: CorrelationId


class ProjectMutationResponse(ApiModel):
    project: Project


class PreflightResponse(ApiModel):
    project: Project
    result: ProjectPreflightResult


class CheckpointCreateRequest(ApiModel):
    reason: CheckpointReason = CheckpointReason.MANUAL
    correlation_id: CorrelationId


class CheckpointListResponse(ApiModel):
    checkpoints: tuple[ProjectCheckpoint, ...]


class RestorePlanRequest(ApiModel):
    correlation_id: CorrelationId


class RestorePlanResponse(ApiModel):
    plan: CheckpointRestorePlan
    protection_checkpoint: ProjectCheckpoint


class CheckpointRestoreRequest(ApiModel):
    protection_checkpoint_id: str = Field(pattern=r"^checkpoint_[a-z0-9]+$")
    expected_project_version: int = Field(gt=0)
    correlation_id: CorrelationId


class CheckpointRestoreResponse(ApiModel):
    result: CheckpointRestoreResult
    project: Project


class ExternalChangeScanRequest(ApiModel):
    baseline_checkpoint_id: str = Field(pattern=r"^checkpoint_[a-z0-9]+$")
    agent_checkpoint_id: str | None = Field(
        default=None,
        pattern=r"^checkpoint_[a-z0-9]+$",
    )
    correlation_id: CorrelationId


class ExternalChangeScanResponse(ApiModel):
    current_checkpoint: ProjectCheckpoint
    changes: tuple[ExternalChange, ...]
    conflicts: tuple[FileConflict, ...]


class ConflictListResponse(ApiModel):
    conflicts: tuple[FileConflict, ...]


class ExternalChangeListResponse(ApiModel):
    changes: tuple[ExternalChange, ...]


class ConflictResolveRequest(ApiModel):
    resolution: ConflictResolution
    expected_conflict_version: int = Field(gt=0)
    expected_project_version: int = Field(gt=0)
    agent_checkpoint_id: str | None = Field(
        default=None,
        pattern=r"^checkpoint_[a-z0-9]+$",
    )
    merged_content_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    correlation_id: CorrelationId


class ConflictResolveResponse(ApiModel):
    conflict: FileConflict
    project: Project
    protection_checkpoint_id: str | None


@router.get("", response_model=ProjectListResponse)
async def list_projects(request: Request) -> ProjectListResponse:
    projects = await _service(request).list_projects()
    return ProjectListResponse(projects=projects)


@router.post("", response_model=ProjectCreateResponse, status_code=201)
async def create_project(
    payload: ProjectCreateRequest,
    request: Request,
) -> ProjectCreateResponse:
    created = await _service(request).create_project(
        name=payload.name,
        goal=payload.goal,
        local_working_directory=payload.local_working_directory,
        workspace_mode=payload.workspace_mode,
        correlation_id=payload.correlation_id,
    )
    return ProjectCreateResponse(
        registration=created.registration,
        manifest=created.manifest,
    )


@router.get("/{project_id}", response_model=ProjectRegistration)
async def get_project(project_id: ProjectIdPath, request: Request) -> ProjectRegistration:
    return await _service(request).get_project(project_id)


@router.post("/{project_id}/open", response_model=ProjectRegistration)
async def open_project(
    project_id: ProjectIdPath,
    payload: ProjectVersionCommand,
    request: Request,
) -> ProjectRegistration:
    return await _service(request).open_project(
        project_id,
        expected_version=payload.expected_version,
        correlation_id=payload.correlation_id,
    )


@router.post("/{project_id}/close", response_model=ProjectMutationResponse)
async def close_project(
    project_id: ProjectIdPath,
    payload: ProjectVersionCommand,
    request: Request,
) -> ProjectMutationResponse:
    project = await _service(request).close_project(
        project_id,
        expected_version=payload.expected_version,
        correlation_id=payload.correlation_id,
    )
    return ProjectMutationResponse(project=project)


@router.post("/{project_id}/preflight", response_model=PreflightResponse)
async def run_preflight(
    project_id: ProjectIdPath,
    payload: ProjectVersionCommand,
    request: Request,
) -> PreflightResponse:
    execution = await _service(request).run_preflight(
        project_id,
        expected_version=payload.expected_version,
        correlation_id=payload.correlation_id,
    )
    return PreflightResponse(project=execution.project, result=execution.result)


@router.get("/{project_id}/preflight", response_model=ProjectPreflightResult)
async def get_preflight(project_id: ProjectIdPath, request: Request) -> ProjectPreflightResult:
    return await _service(request).get_preflight(project_id)


@router.post("/{project_id}/checkpoints", response_model=ProjectCheckpoint, status_code=201)
async def create_checkpoint(
    project_id: ProjectIdPath,
    payload: CheckpointCreateRequest,
    request: Request,
) -> ProjectCheckpoint:
    return await _service(request).create_checkpoint(
        project_id,
        reason=payload.reason,
        correlation_id=payload.correlation_id,
    )


@router.get("/{project_id}/checkpoints", response_model=CheckpointListResponse)
async def list_checkpoints(
    project_id: ProjectIdPath,
    request: Request,
) -> CheckpointListResponse:
    checkpoints = await _service(request).list_checkpoints(project_id)
    return CheckpointListResponse(checkpoints=checkpoints)


@router.post(
    "/{project_id}/checkpoints/{checkpoint_id}/restore-plan",
    response_model=RestorePlanResponse,
)
async def plan_restore(
    project_id: ProjectIdPath,
    checkpoint_id: CheckpointIdPath,
    payload: RestorePlanRequest,
    request: Request,
) -> RestorePlanResponse:
    planning = await _service(request).plan_restore(
        project_id,
        checkpoint_id,
        correlation_id=payload.correlation_id,
    )
    return RestorePlanResponse(
        plan=planning.plan,
        protection_checkpoint=planning.protection_checkpoint,
    )


@router.post(
    "/{project_id}/checkpoints/{checkpoint_id}/restore",
    response_model=CheckpointRestoreResponse,
)
async def restore_checkpoint(
    project_id: ProjectIdPath,
    checkpoint_id: CheckpointIdPath,
    payload: CheckpointRestoreRequest,
    request: Request,
) -> CheckpointRestoreResponse:
    execution = await _service(request).restore_checkpoint(
        project_id,
        checkpoint_id,
        protection_checkpoint_id=payload.protection_checkpoint_id,
        expected_project_version=payload.expected_project_version,
        correlation_id=payload.correlation_id,
    )
    return CheckpointRestoreResponse(result=execution.result, project=execution.project)


@router.post("/{project_id}/external-changes/scan", response_model=ExternalChangeScanResponse)
async def scan_external_changes(
    project_id: ProjectIdPath,
    payload: ExternalChangeScanRequest,
    request: Request,
) -> ExternalChangeScanResponse:
    scan = await _service(request).scan_external_changes(
        project_id,
        baseline_checkpoint_id=payload.baseline_checkpoint_id,
        agent_checkpoint_id=payload.agent_checkpoint_id,
        correlation_id=payload.correlation_id,
    )
    return ExternalChangeScanResponse(
        current_checkpoint=scan.current_checkpoint,
        changes=scan.changes,
        conflicts=scan.conflicts,
    )


@router.get("/{project_id}/external-changes", response_model=ExternalChangeListResponse)
async def list_external_changes(
    project_id: ProjectIdPath,
    request: Request,
) -> ExternalChangeListResponse:
    changes = await _service(request).list_external_changes(project_id)
    return ExternalChangeListResponse(changes=changes)


@router.get("/{project_id}/conflicts", response_model=ConflictListResponse)
async def list_conflicts(
    project_id: ProjectIdPath,
    request: Request,
) -> ConflictListResponse:
    conflicts = await _service(request).list_conflicts(project_id)
    return ConflictListResponse(conflicts=conflicts)


@router.post(
    "/{project_id}/conflicts/{conflict_id}/resolve",
    response_model=ConflictResolveResponse,
)
async def resolve_conflict(
    project_id: ProjectIdPath,
    conflict_id: ConflictIdPath,
    payload: ConflictResolveRequest,
    request: Request,
) -> ConflictResolveResponse:
    execution = await _service(request).resolve_conflict(
        project_id,
        conflict_id,
        resolution=payload.resolution,
        expected_conflict_version=payload.expected_conflict_version,
        expected_project_version=payload.expected_project_version,
        agent_checkpoint_id=payload.agent_checkpoint_id,
        merged_content_hash=payload.merged_content_hash,
        correlation_id=payload.correlation_id,
    )
    return ConflictResolveResponse(
        conflict=execution.conflict,
        project=execution.project,
        protection_checkpoint_id=execution.protection_checkpoint_id,
    )


def _service(request: Request) -> ProjectApplicationService:
    return cast(ProjectApplicationService, request.app.state.project_service)
