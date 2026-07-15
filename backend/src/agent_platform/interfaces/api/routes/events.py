from __future__ import annotations

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field

from agent_platform.application.events import EventStreamService, IssuedEventTicket
from agent_platform.domain.events import EventEnvelope

ticket_router = APIRouter(prefix="/events", tags=["events"])
websocket_router = APIRouter(tags=["events"])
WorkflowId = Annotated[str, Field(pattern=r"^workflow_[a-z0-9]+$")]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class EventTicketRequest(ApiModel):
    workflow_id: WorkflowId


class EventTicketResponse(ApiModel):
    ticket: str
    workflow_id: str
    expires_at: str
    websocket_path: Literal["/api/v1/events/ws"] = "/api/v1/events/ws"


class EventReplayResponse(ApiModel):
    events: tuple[EventEnvelope, ...]


@ticket_router.post("/tickets", response_model=EventTicketResponse, status_code=201)
async def issue_event_ticket(
    payload: EventTicketRequest,
    request: Request,
) -> EventTicketResponse:
    issued = await _request_service(request).issue_ticket(payload.workflow_id)
    return _ticket_response(issued)


@ticket_router.get("/replay", response_model=EventReplayResponse)
async def replay_events(
    request: Request,
    workflow_id: Annotated[str, Query(pattern=r"^workflow_[a-z0-9]+$")],
    after_event_id: Annotated[int, Query(ge=0)] = 0,
) -> EventReplayResponse:
    events = await _request_service(request).replay(
        workflow_id,
        after_event_id=after_event_id,
    )
    return EventReplayResponse(events=events)


@websocket_router.websocket("/events/ws")
async def stream_events(
    websocket: WebSocket,
    ticket: str,
    after_event_id: int = 0,
) -> None:
    service = cast(EventStreamService, websocket.app.state.event_stream_service)
    consumed = await service.consume_ticket(ticket)
    if consumed is None or after_event_id < 0:
        await websocket.close(code=4401)
        return
    subscription = await service.subscribe(consumed.workflow_id)
    await websocket.accept()
    last_event_id = after_event_id
    try:
        while True:
            replay = await service.replay(
                consumed.workflow_id,
                after_event_id=last_event_id,
            )
            for envelope in replay:
                last_event_id = await _send_event(websocket, envelope, last_event_id)
            if len(replay) < service.replay_batch_size:
                break
        await websocket.send_json(
            {
                "schema_version": 1,
                "type": "ready",
                "last_event_id": last_event_id,
            }
        )
        while True:
            queued = await subscription.queue.get()
            if queued is None:
                await websocket.close(code=1013)
                return
            last_event_id = await _send_event(websocket, queued, last_event_id)
    except WebSocketDisconnect:
        return
    finally:
        await service.unsubscribe(subscription.id)


async def _send_event(
    websocket: WebSocket,
    envelope: EventEnvelope,
    last_event_id: int,
) -> int:
    event_id = envelope.event_id
    if event_id is None or event_id <= last_event_id:
        return last_event_id
    await websocket.send_json(
        {
            "schema_version": 1,
            "type": "event",
            "event_id": event_id,
            "event": envelope.model_dump(mode="json"),
        }
    )
    return event_id


def _ticket_response(issued: IssuedEventTicket) -> EventTicketResponse:
    return EventTicketResponse(
        ticket=issued.ticket,
        workflow_id=issued.workflow_id,
        expires_at=issued.expires_at.isoformat(),
    )


def _request_service(request: Request) -> EventStreamService:
    return cast(EventStreamService, request.app.state.event_stream_service)
