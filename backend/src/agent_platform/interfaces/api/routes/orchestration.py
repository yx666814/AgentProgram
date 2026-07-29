from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import APIRouter, Request
from fastapi import Path as ApiPath
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from agent_platform.application.orchestration import OrchestrationApplicationService

router = APIRouter(tags=["orchestration"])
WorkflowIdPath = Annotated[str, ApiPath(pattern=r"^workflow_[a-z0-9]+$")]
CorrelationId = Annotated[str, Field(min_length=1, max_length=120)]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class OrchestrationRequest(ApiModel):
    request_key: str = Field(
        min_length=16,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )
    instruction: str = Field(min_length=1, max_length=100_000)
    correlation_id: CorrelationId


@router.post("/workflows/{workflow_id}/orchestration/stream")
async def orchestrate_workflow_stage(
    workflow_id: WorkflowIdPath,
    payload: OrchestrationRequest,
    request: Request,
) -> StreamingResponse:
    service = cast(OrchestrationApplicationService, request.app.state.orchestration_service)

    async def frames() -> AsyncIterator[str]:
        async for frame in service.stream_stage(
            workflow_id,
            request_key=payload.request_key,
            instruction=payload.instruction,
            correlation_id=payload.correlation_id,
        ):
            yield frame.model_dump_json() + "\n"

    return StreamingResponse(
        frames(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
