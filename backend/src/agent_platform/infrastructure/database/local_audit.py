from __future__ import annotations

import asyncio
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent_platform.domain.events.models import EventEnvelope
from agent_platform.domain.events.outbox import OutboxDeliveryState
from agent_platform.infrastructure.database.models import LocalAuditEventRow, OutboxDeliveryRow
from agent_platform.infrastructure.database.outbox_store import SqlAlchemyOutboxStore
from agent_platform.infrastructure.database.write_serialization import serialized_write
from agent_platform.ports.event_publishing import LOCAL_AUDIT_CONSUMER


class LocalAuditPublisher:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        write_lock: asyncio.Lock | None = None,
    ) -> None:
        self._sessions = session_factory
        self._write_lock = write_lock

    @property
    def consumer_name(self) -> str:
        return LOCAL_AUDIT_CONSUMER

    async def publish(
        self,
        envelope: EventEnvelope,
        *,
        idempotency_key: int,
        delivery_id: str,
        lease_token: str,
        delivered_at: datetime,
    ) -> None:
        async with serialized_write(self._write_lock):
            async with self._sessions.begin() as session:
                owned = await session.scalar(
                    select(OutboxDeliveryRow.id).where(
                        OutboxDeliveryRow.id == delivery_id,
                        OutboxDeliveryRow.event_log_id == idempotency_key,
                        OutboxDeliveryRow.consumer_name == LOCAL_AUDIT_CONSUMER,
                        OutboxDeliveryRow.delivery_state == OutboxDeliveryState.LEASED.value,
                        OutboxDeliveryRow.lease_token == lease_token,
                    )
                )
                if owned is None:
                    return
                await session.execute(
                    insert(LocalAuditEventRow)
                    .values(
                        event_log_id=idempotency_key,
                        event_type=envelope.event_type,
                        correlation_id=envelope.correlation_id,
                        causation_id=envelope.causation_id,
                        project_id=envelope.project_id,
                        workflow_id=envelope.workflow_id,
                        room_id=envelope.room_id,
                        task_id=envelope.task_id,
                        occurred_at=envelope.occurred_at,
                        delivered_at=delivered_at,
                    )
                    .on_conflict_do_nothing(index_elements=[LocalAuditEventRow.event_log_id])
                )
                result = await session.execute(
                    update(OutboxDeliveryRow)
                    .where(
                        OutboxDeliveryRow.id == delivery_id,
                        OutboxDeliveryRow.delivery_state == OutboxDeliveryState.LEASED.value,
                        OutboxDeliveryRow.lease_token == lease_token,
                    )
                    .values(
                        delivery_state=OutboxDeliveryState.DELIVERED.value,
                        delivered_at=delivered_at,
                        lease_owner=None,
                        lease_token=None,
                        lease_expires_at=None,
                        last_error_category=None,
                    )
                )
                if getattr(result, "rowcount", 0) == 1:
                    await SqlAlchemyOutboxStore._refresh_aggregate(
                        session, idempotency_key, delivered_at
                    )
