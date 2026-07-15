import asyncio
from datetime import timedelta

import pytest

from agent_platform.application.events import EventTicketStore


@pytest.mark.asyncio
async def test_event_ticket_is_single_use() -> None:
    store = EventTicketStore(timedelta(seconds=1))
    issued = await store.issue("workflow_1")

    consumed = await store.consume(issued.ticket)

    assert consumed is not None
    assert consumed.workflow_id == "workflow_1"
    assert await store.consume(issued.ticket) is None


@pytest.mark.asyncio
async def test_event_ticket_expires() -> None:
    store = EventTicketStore(timedelta(milliseconds=1))
    issued = await store.issue("workflow_1")

    await asyncio.sleep(0.01)

    assert await store.consume(issued.ticket) is None
