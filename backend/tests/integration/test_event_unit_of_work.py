from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select

from agent_platform.infrastructure.database.base import Base
from agent_platform.infrastructure.database.models import EventLogRow, OutboxEventRow
from agent_platform.infrastructure.database.session import create_database
from agent_platform.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork


@pytest.mark.asyncio
async def test_commit_persists_event_and_outbox_atomically(tmp_path: Path) -> None:
    database = create_database(tmp_path / "agent.db")
    occurred_at = datetime.now(UTC)

    try:
        async with database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with SqlAlchemyUnitOfWork(database.sessions) as uow:
            event_id = await uow.events.append(
                event_type="workflow.started",
                aggregate_type="workflow",
                aggregate_id="wf_1",
                payload={"mode": "MANUAL"},
                occurred_at=occurred_at,
                project_id="project_1",
                workflow_id="wf_1",
            )
            outbox_id = await uow.outbox.enqueue(event_id)
            await uow.commit()

        async with database.sessions() as session:
            events = (await session.scalars(select(EventLogRow))).all()
            outbox_events = (await session.scalars(select(OutboxEventRow))).all()
    finally:
        await database.dispose()

    assert len(events) == 1
    assert len(outbox_events) == 1

    event = events[0]
    assert event.event_id == event_id
    assert event.event_type == "workflow.started"
    assert event.aggregate_type == "workflow"
    assert event.aggregate_id == "wf_1"
    assert event.payload == {"mode": "MANUAL"}
    assert event.created_at == occurred_at
    assert event.project_id == "project_1"
    assert event.workflow_id == "wf_1"
    assert event.room_id is None
    assert event.task_id is None

    outbox_event = outbox_events[0]
    assert outbox_event.id == outbox_id
    assert outbox_event.event_log_id == event_id
    assert outbox_event.delivery_state == "pending"
    assert outbox_event.attempt_count == 0
    assert outbox_event.created_at.tzinfo is UTC
    assert outbox_event.last_attempt_at is None
    assert outbox_event.delivered_at is None


@pytest.mark.asyncio
async def test_exception_rolls_back_event_and_outbox(tmp_path: Path) -> None:
    database = create_database(tmp_path / "agent.db")

    try:
        async with database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        with pytest.raises(RuntimeError, match="abort unit of work"):
            async with SqlAlchemyUnitOfWork(database.sessions) as uow:
                event_id = await uow.events.append(
                    event_type="workflow.started",
                    aggregate_type="workflow",
                    aggregate_id="wf_1",
                    payload={"mode": "MANUAL"},
                    occurred_at=datetime.now(UTC),
                    project_id="project_1",
                    workflow_id="wf_1",
                )
                await uow.outbox.enqueue(event_id)
                raise RuntimeError("abort unit of work")

        async with database.sessions() as session:
            event_count = await session.scalar(select(func.count()).select_from(EventLogRow))
            outbox_count = await session.scalar(
                select(func.count()).select_from(OutboxEventRow)
            )
    finally:
        await database.dispose()

    assert event_count == 0
    assert outbox_count == 0


@pytest.mark.asyncio
async def test_normal_exit_without_commit_rolls_back_event_and_outbox(tmp_path: Path) -> None:
    database = create_database(tmp_path / "agent.db")

    try:
        async with database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with SqlAlchemyUnitOfWork(database.sessions) as uow:
            event_id = await uow.events.append(
                event_type="workflow.started",
                aggregate_type="workflow",
                aggregate_id="wf_1",
                payload={"mode": "MANUAL"},
                occurred_at=datetime.now(UTC),
                project_id="project_1",
                workflow_id="wf_1",
            )
            await uow.outbox.enqueue(event_id)

        async with database.sessions() as session:
            event_count = await session.scalar(select(func.count()).select_from(EventLogRow))
            outbox_count = await session.scalar(
                select(func.count()).select_from(OutboxEventRow)
            )
    finally:
        await database.dispose()

    assert event_count == 0
    assert outbox_count == 0
