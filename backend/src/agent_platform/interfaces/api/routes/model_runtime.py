from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import APIRouter, Request
from fastapi import Path as ApiPath
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from agent_platform.application.model_runtime import (
    AgentRuntimeService,
    ModelConfigurationService,
)
from agent_platform.domain.model_runtime import (
    AgentRun,
    AgentRunSnapshot,
    ModelProfile,
    ModelProvider,
    RoomModelAssignment,
)

router = APIRouter(tags=["model-runtime"])
CorrelationId = Annotated[str, Field(min_length=1, max_length=120)]
ProfileIdPath = Annotated[str, ApiPath(pattern=r"^profile_[a-z0-9]+$")]
RoomIdPath = Annotated[str, ApiPath(pattern=r"^room_[a-z0-9]+$")]
AgentRunIdPath = Annotated[str, ApiPath(pattern=r"^agentrun_[a-z0-9]+$")]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class ModelProfileCreateRequest(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    provider: ModelProvider
    base_url: str = Field(min_length=1, max_length=2048)
    model: str = Field(min_length=1, max_length=200)
    credential_ref: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[a-z][a-z0-9_.:-]+$",
    )
    masked_hint: str = Field(min_length=1, max_length=40)
    correlation_id: CorrelationId


class ModelProfileUpdateRequest(ModelProfileCreateRequest):
    enabled: bool
    expected_version: int = Field(gt=0)


class ModelProfileListResponse(ApiModel):
    profiles: tuple[ModelProfile, ...]


class RoomAssignmentRequest(ApiModel):
    primary_profile_id: str = Field(pattern=r"^profile_[a-z0-9]+$")
    reviewer_a_profile_id: str | None = Field(
        default=None,
        pattern=r"^profile_[a-z0-9]+$",
    )
    reviewer_b_profile_id: str | None = Field(
        default=None,
        pattern=r"^profile_[a-z0-9]+$",
    )
    expected_version: int | None = Field(default=None, gt=0)
    correlation_id: CorrelationId


class AgentRunCreateRequest(ApiModel):
    request_key: str = Field(
        min_length=16,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )
    formal: bool = False
    correlation_id: CorrelationId


class AgentRunCreateResponse(ApiModel):
    run: AgentRun
    created: bool


class AgentRunListResponse(ApiModel):
    runs: tuple[AgentRun, ...]


class AgentRunStreamRequest(ApiModel):
    instruction: str = Field(min_length=1, max_length=100_000)
    correlation_id: CorrelationId


class AgentRunCancelResponse(ApiModel):
    run: AgentRun
    cancellation_requested: bool


@router.post("/model-profiles", response_model=ModelProfile, status_code=201)
async def create_profile(
    payload: ModelProfileCreateRequest,
    request: Request,
) -> ModelProfile:
    return await _configuration(request).create_profile(
        name=payload.name,
        provider=payload.provider,
        base_url=payload.base_url,
        model=payload.model,
        credential_ref=payload.credential_ref,
        masked_hint=payload.masked_hint,
        correlation_id=payload.correlation_id,
    )


@router.get("/model-profiles", response_model=ModelProfileListResponse)
async def list_profiles(request: Request) -> ModelProfileListResponse:
    profiles = await _configuration(request).list_profiles()
    return ModelProfileListResponse(profiles=profiles)


@router.get("/model-profiles/{profile_id}", response_model=ModelProfile)
async def get_profile(profile_id: ProfileIdPath, request: Request) -> ModelProfile:
    return await _configuration(request).get_profile(profile_id)


@router.put("/model-profiles/{profile_id}", response_model=ModelProfile)
async def update_profile(
    profile_id: ProfileIdPath,
    payload: ModelProfileUpdateRequest,
    request: Request,
) -> ModelProfile:
    return await _configuration(request).update_profile(
        profile_id,
        name=payload.name,
        provider=payload.provider,
        base_url=payload.base_url,
        model=payload.model,
        credential_ref=payload.credential_ref,
        masked_hint=payload.masked_hint,
        enabled=payload.enabled,
        expected_version=payload.expected_version,
        correlation_id=payload.correlation_id,
    )


@router.put("/rooms/{room_id}/model-assignment", response_model=RoomModelAssignment)
async def assign_room_models(
    room_id: RoomIdPath,
    payload: RoomAssignmentRequest,
    request: Request,
) -> RoomModelAssignment:
    return await _configuration(request).assign_room(
        room_id,
        primary_profile_id=payload.primary_profile_id,
        reviewer_a_profile_id=payload.reviewer_a_profile_id,
        reviewer_b_profile_id=payload.reviewer_b_profile_id,
        expected_version=payload.expected_version,
        correlation_id=payload.correlation_id,
    )


@router.get("/rooms/{room_id}/model-assignment", response_model=RoomModelAssignment)
async def get_room_assignment(
    room_id: RoomIdPath,
    request: Request,
) -> RoomModelAssignment:
    return await _configuration(request).get_assignment(room_id)


@router.post("/rooms/{room_id}/agent-runs", response_model=AgentRunCreateResponse)
async def create_agent_run(
    room_id: RoomIdPath,
    payload: AgentRunCreateRequest,
    request: Request,
) -> AgentRunCreateResponse:
    creation = await _runtime(request).create_run(
        room_id,
        request_key=payload.request_key,
        formal=payload.formal,
        correlation_id=payload.correlation_id,
    )
    return AgentRunCreateResponse(run=creation.run, created=creation.created)


@router.get("/rooms/{room_id}/agent-runs", response_model=AgentRunListResponse)
async def list_agent_runs(
    room_id: RoomIdPath,
    request: Request,
) -> AgentRunListResponse:
    runs = await _runtime(request).list_runs(room_id)
    return AgentRunListResponse(runs=runs)


@router.get("/agent-runs/{run_id}", response_model=AgentRunSnapshot)
async def get_agent_run(run_id: AgentRunIdPath, request: Request) -> AgentRunSnapshot:
    return await _runtime(request).get_run(run_id)


@router.get("/agent-runs/{run_id}/output", response_class=PlainTextResponse)
async def get_agent_run_output(run_id: AgentRunIdPath, request: Request) -> PlainTextResponse:
    output = await _runtime(request).get_output(run_id)
    return PlainTextResponse(output, media_type="text/plain; charset=utf-8")


@router.post("/agent-runs/{run_id}/stream")
async def stream_agent_run(
    run_id: AgentRunIdPath,
    payload: AgentRunStreamRequest,
    request: Request,
) -> StreamingResponse:
    service = _runtime(request)

    async def frames() -> AsyncIterator[str]:
        async for frame in service.stream_run(
            run_id,
            instruction=payload.instruction,
            correlation_id=payload.correlation_id,
        ):
            yield frame.model_dump_json() + "\n"

    return StreamingResponse(
        frames(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/agent-runs/{run_id}/cancel", response_model=AgentRunCancelResponse)
async def cancel_agent_run(
    run_id: AgentRunIdPath,
    request: Request,
) -> AgentRunCancelResponse:
    before = await _runtime(request).get_run(run_id)
    run = await _runtime(request).cancel_run(run_id)
    return AgentRunCancelResponse(
        run=run,
        cancellation_requested=before.run.status.value in {"pending", "running"},
    )


def _configuration(request: Request) -> ModelConfigurationService:
    return cast(ModelConfigurationService, request.app.state.model_configuration_service)


def _runtime(request: Request) -> AgentRuntimeService:
    return cast(AgentRuntimeService, request.app.state.agent_runtime_service)
