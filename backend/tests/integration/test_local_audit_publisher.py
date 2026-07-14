from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from agent_platform.domain.events import ActorRef, ActorType, EventEnvelope, EventSource
from agent_platform.infrastructure.database.base import Base
from agent_platform.infrastructure.database.local_audit import LocalAuditPublisher
from agent_platform.infrastructure.database.models import (
    LocalAuditEventRow,
    OutboxDeliveryRow,
    OutboxEventRow,
)
from agent_platform.infrastructure.database.outbox_store import SqlAlchemyOutboxStore
from agent_platform.infrastructure.database.session import create_database
from agent_platform.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork


@pytest.mark.asyncio
async def test_local_audit_side_effect_and_receipt_are_atomic_and_idempotent(
    tmp_path: Path,
) -> None:
    database = create_database(tmp_path / "agent.db")
    envelope = EventEnvelope(
        schema_version=1,
        event_type="workflow.started",
        correlation_id="correlation_1",
        actor=ActorRef(type=ActorType.SYSTEM),
        source=EventSource.BACKEND,
        occurred_at=datetime.now(UTC),
        project_id="project_1",
        payload={"secret": "not projected"},
    )
    try:
        async with database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with SqlAlchemyUnitOfWork(database.sessions) as uow:
            event_id = await uow.events.append(
                envelope=envelope,
                aggregate_type="workflow",
                aggregate_id="wf_1",
            )
            await uow.commit()
        store = SqlAlchemyOutboxStore(
            database.sessions,
            lease_owner="dispatcher_1",
            lease_seconds=60,
            max_attempts=3,
            backoff_base_seconds=1,
            backoff_max_seconds=10,
            recovery_batch_size=10,
        )
        claim = await store.claim_next()
        assert claim is not None
        publisher = LocalAuditPublisher(database.sessions)
        delivered_at = datetime.now(UTC)
        await publisher.publish(
            claim.envelope,
            idempotency_key=claim.event_id,
            delivery_id=claim.delivery_id,
            lease_token=claim.lease_token,
            delivered_at=delivered_at,
        )
        await publisher.publish(
            claim.envelope,
            idempotency_key=claim.event_id,
            delivery_id=claim.delivery_id,
            lease_token=claim.lease_token,
            delivered_at=delivered_at,
        )

        async with database.sessions() as session:
            audits = (await session.scalars(select(LocalAuditEventRow))).all()
            delivery = (await session.scalars(select(OutboxDeliveryRow))).one()
            aggregate = (await session.scalars(select(OutboxEventRow))).one()
    finally:
        await database.dispose()

    assert len(audits) == 1
    assert audits[0].event_log_id == event_id
    assert not hasattr(audits[0], "payload")
    assert delivery.delivery_state == "delivered"
    assert aggregate.delivery_state == "delivered"
