import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from agent_platform.application.events.outbox_dispatcher import OutboxDispatcher
from agent_platform.domain.events import ActorRef, ActorType, EventEnvelope, EventSource
from agent_platform.infrastructure.database.base import Base
from agent_platform.infrastructure.database.local_audit import LocalAuditPublisher
from agent_platform.infrastructure.database.models import LocalAuditEventRow
from agent_platform.infrastructure.database.outbox_store import SqlAlchemyOutboxStore
from agent_platform.infrastructure.database.session import create_database
from agent_platform.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork


@pytest.mark.asyncio
async def test_dispatcher_delivers_pending_event_to_local_audit(tmp_path: Path) -> None:
    database = create_database(tmp_path / "agent.db")
    try:
        async with database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with SqlAlchemyUnitOfWork(database.sessions) as uow:
            event_id = await uow.events.append(
                envelope=EventEnvelope(
                    schema_version=1,
                    event_type="workflow.started",
                    correlation_id="correlation_1",
                    actor=ActorRef(type=ActorType.SYSTEM),
                    source=EventSource.BACKEND,
                    occurred_at=datetime.now(UTC),
                    payload={},
                ),
                aggregate_type="workflow",
                aggregate_id="wf_1",
            )
            await uow.commit()
        store = SqlAlchemyOutboxStore(
            database.sessions,
            lease_owner="dispatcher_1",
            lease_seconds=1,
            max_attempts=3,
            backoff_base_seconds=0.01,
            backoff_max_seconds=0.1,
            recovery_batch_size=10,
        )
        dispatcher = OutboxDispatcher(
            store=store,
            publishers=(LocalAuditPublisher(database.sessions),),
            poll_interval_seconds=0.01,
            publish_timeout_seconds=0.5,
            cleanup_interval_seconds=60,
            delivered_retention=timedelta(days=1),
            cleanup_batch_size=10,
        )
        task = asyncio.create_task(dispatcher.run())
        try:
            for _ in range(100):
                async with database.sessions() as session:
                    audit = await session.scalar(
                        select(LocalAuditEventRow).where(
                            LocalAuditEventRow.event_log_id == event_id
                        )
                    )
                if audit is not None:
                    break
                await asyncio.sleep(0.01)
            else:
                raise AssertionError("dispatcher did not deliver local audit event")
        finally:
            dispatcher.request_stop()
            await asyncio.wait_for(task, timeout=1)
    finally:
        await database.dispose()
