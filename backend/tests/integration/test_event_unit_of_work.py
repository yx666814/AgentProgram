import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, cast

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import InvalidRequestError

from agent_platform.infrastructure.database.base import Base
from agent_platform.infrastructure.database.models import EventLogRow, OutboxEventRow
from agent_platform.infrastructure.database.session import create_database
from agent_platform.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork


class _PoolWithCheckedOut(Protocol):
    def checkedout(self) -> int: ...


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
            outbox_count = await session.scalar(select(func.count()).select_from(OutboxEventRow))
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
            outbox_count = await session.scalar(select(func.count()).select_from(OutboxEventRow))
    finally:
        await database.dispose()

    assert event_count == 0
    assert outbox_count == 0


@pytest.mark.asyncio
async def test_unit_of_work_rejects_commands_outside_active_context(tmp_path: Path) -> None:
    database = create_database(tmp_path / "agent.db")
    uow = SqlAlchemyUnitOfWork(database.sessions)

    try:
        with pytest.raises(RuntimeError, match="unit of work is not active"):
            await uow.commit()
        with pytest.raises(RuntimeError, match="unit of work is not active"):
            await uow.rollback()

        async with uow:
            pass

        with pytest.raises(RuntimeError, match="unit of work is not active"):
            await uow.commit()
        with pytest.raises(RuntimeError, match="unit of work is not active"):
            await uow.rollback()
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_retained_repository_cannot_persist_after_unit_of_work_exit(
    tmp_path: Path,
) -> None:
    database = create_database(tmp_path / "agent.db")

    try:
        async with database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        uow = SqlAlchemyUnitOfWork(database.sessions)
        async with uow:
            events = uow.events

        repository_error: InvalidRequestError | None = None
        try:
            await events.append(
                event_type="reuse.persisted",
                aggregate_type="test",
                aggregate_id="test_1",
                payload={},
                occurred_at=datetime.now(UTC),
            )
        except InvalidRequestError as exc:
            repository_error = exc
        else:
            await uow.session.commit()

        async with database.sessions() as session:
            event_count = await session.scalar(select(func.count()).select_from(EventLogRow))
    finally:
        await database.dispose()

    assert event_count == 0
    assert repository_error is not None
    assert "permanently closed" in str(repository_error)


@pytest.mark.asyncio
async def test_repeated_cancellation_waits_for_active_transaction_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = create_database(tmp_path / "agent.db")
    uow = SqlAlchemyUnitOfWork(database.sessions)
    allow_close = asyncio.Event()
    close_completed = asyncio.Event()
    close_started = asyncio.Event()
    original_close: Callable[[], Awaitable[None]] | None = None

    try:
        async with database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        await uow.__aenter__()
        await uow.commit()
        await uow.events.append(
            event_type="workflow.started",
            aggregate_type="workflow",
            aggregate_id="wf_1",
            payload={"mode": "MANUAL"},
            occurred_at=datetime.now(UTC),
            project_id="project_1",
            workflow_id="wf_1",
        )

        original_close = uow.session.close

        async def slow_close() -> None:
            close_started.set()
            await allow_close.wait()
            await original_close()
            close_completed.set()

        monkeypatch.setattr(uow.session, "close", slow_close)
        assert uow.session.in_transaction()
        exit_task = asyncio.create_task(uow.__aexit__(None, None, None))
        await asyncio.wait_for(close_started.wait(), timeout=1)

        exit_task.cancel()
        await asyncio.sleep(0)
        assert not exit_task.done()
        exit_task.cancel()
        await asyncio.sleep(0)
        escaped_before_close = exit_task.done()

        allow_close.set()
        with pytest.raises(asyncio.CancelledError):
            await exit_task
        cleanup_completed = close_completed.is_set()

        repository_error: InvalidRequestError | None = None
        try:
            await uow.events.append(
                event_type="reuse.persisted",
                aggregate_type="test",
                aggregate_id="test_1",
                payload={},
                occurred_at=datetime.now(UTC),
            )
        except InvalidRequestError as exc:
            repository_error = exc
        else:
            await uow.session.commit()

        pool = cast(_PoolWithCheckedOut, database.engine.sync_engine.pool)
        checked_out = pool.checkedout()
        in_transaction = uow.session.in_transaction()
        async with database.sessions() as session:
            event_count = await session.scalar(select(func.count()).select_from(EventLogRow))
    finally:
        allow_close.set()
        if original_close is not None and not close_completed.is_set():
            await original_close()
        await database.dispose()

    assert (
        escaped_before_close,
        cleanup_completed,
        checked_out,
        in_transaction,
        event_count,
    ) == (
        False,
        True,
        0,
        False,
        0,
    )
    assert repository_error is not None
    assert "permanently closed" in str(repository_error)
