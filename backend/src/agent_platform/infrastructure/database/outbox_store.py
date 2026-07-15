from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import Integer, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent_platform.domain.events.outbox import (
    DeliveryErrorCategory,
    OutboxAggregateState,
    OutboxDeliveryState,
    retry_delay,
)
from agent_platform.domain.shared.ids import new_id
from agent_platform.infrastructure.database.models import OutboxDeliveryRow, OutboxEventRow
from agent_platform.infrastructure.database.repositories import EventLogRepository
from agent_platform.infrastructure.database.write_serialization import serialized_write
from agent_platform.ports.event_publishing import ClaimedDelivery


class SqlAlchemyOutboxStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        lease_owner: str,
        lease_seconds: float,
        max_attempts: int,
        backoff_base_seconds: float,
        backoff_max_seconds: float,
        recovery_batch_size: int,
        write_lock: asyncio.Lock | None = None,
    ) -> None:
        self._sessions = session_factory
        self._lease_owner = lease_owner
        self._lease_seconds = lease_seconds
        self._max_attempts = max_attempts
        self._backoff_base = backoff_base_seconds
        self._backoff_max = backoff_max_seconds
        self._recovery_batch_size = recovery_batch_size
        self._write_lock = write_lock

    async def claim_next(self, now: datetime | None = None) -> ClaimedDelivery | None:
        claimed_at = now or datetime.now(UTC)
        lease_token = new_id("lease")
        candidate = (
            select(OutboxDeliveryRow.id)
            .where(
                OutboxDeliveryRow.delivery_state.in_(
                    [OutboxDeliveryState.PENDING.value, OutboxDeliveryState.RETRY_WAIT.value]
                ),
                OutboxDeliveryRow.next_attempt_at <= claimed_at,
                OutboxDeliveryRow.attempt_count < self._max_attempts,
            )
            .order_by(
                OutboxDeliveryRow.next_attempt_at,
                OutboxDeliveryRow.created_at,
                OutboxDeliveryRow.id,
            )
            .limit(1)
            .scalar_subquery()
        )
        statement = (
            update(OutboxDeliveryRow)
            .where(OutboxDeliveryRow.id == candidate)
            .values(
                delivery_state=OutboxDeliveryState.LEASED.value,
                lease_owner=self._lease_owner,
                lease_token=lease_token,
                lease_expires_at=claimed_at + timedelta(seconds=self._lease_seconds),
                attempt_count=OutboxDeliveryRow.attempt_count + 1,
                last_error_category=None,
            )
            .returning(
                OutboxDeliveryRow.id,
                OutboxDeliveryRow.event_log_id,
                OutboxDeliveryRow.consumer_name,
                OutboxDeliveryRow.attempt_count,
            )
        )
        async with serialized_write(self._write_lock):
            async with self._sessions.begin() as session:
                row = (await session.execute(statement)).first()
                if row is None:
                    return None
                envelope = await EventLogRepository(session).get(int(row.event_log_id))
                if envelope is None:
                    raise RuntimeError("claimed outbox event is missing")
                return ClaimedDelivery(
                    delivery_id=str(row.id),
                    event_id=int(row.event_log_id),
                    consumer_name=str(row.consumer_name),
                    lease_token=lease_token,
                    attempt_count=int(row.attempt_count),
                    envelope=envelope,
                )

    async def record_failure(
        self,
        claim: ClaimedDelivery,
        category: DeliveryErrorCategory,
        now: datetime | None = None,
    ) -> bool:
        failed_at = now or datetime.now(UTC)
        terminal = claim.attempt_count >= self._max_attempts
        values: dict[str, object] = {
            "delivery_state": (
                OutboxDeliveryState.DEAD_LETTER.value
                if terminal
                else OutboxDeliveryState.RETRY_WAIT.value
            ),
            "lease_owner": None,
            "lease_token": None,
            "lease_expires_at": None,
            "last_error_category": category.value,
            "dead_lettered_at": failed_at if terminal else None,
        }
        if not terminal:
            values["next_attempt_at"] = failed_at + retry_delay(
                claim.attempt_count,
                base_seconds=self._backoff_base,
                maximum_seconds=self._backoff_max,
            )
        async with serialized_write(self._write_lock):
            async with self._sessions.begin() as session:
                result = await session.execute(
                    update(OutboxDeliveryRow)
                    .where(
                        OutboxDeliveryRow.id == claim.delivery_id,
                        OutboxDeliveryRow.delivery_state == OutboxDeliveryState.LEASED.value,
                        OutboxDeliveryRow.lease_token == claim.lease_token,
                    )
                    .values(**values)
                )
                if getattr(result, "rowcount", 0) != 1:
                    return False
                await self._refresh_aggregate(session, claim.event_id, failed_at)
                return True

    async def recover_expired_leases(self, now: datetime | None = None) -> int:
        recovered_at = now or datetime.now(UTC)
        async with self._sessions() as session:
            rows = (
                await session.execute(
                    select(OutboxDeliveryRow)
                    .where(
                        OutboxDeliveryRow.delivery_state == OutboxDeliveryState.LEASED.value,
                        OutboxDeliveryRow.lease_expires_at <= recovered_at,
                    )
                    .limit(self._recovery_batch_size)
                )
            ).scalars()
            claims: list[ClaimedDelivery] = []
            repository = EventLogRepository(session)
            for row in rows:
                envelope = await repository.get(row.event_log_id)
                if envelope is None or row.lease_token is None:
                    continue
                claims.append(
                    ClaimedDelivery(
                        delivery_id=row.id,
                        event_id=row.event_log_id,
                        consumer_name=row.consumer_name,
                        lease_token=row.lease_token,
                        attempt_count=row.attempt_count,
                        envelope=envelope,
                    )
                )
        count = 0
        for claim in claims:
            if await self.record_failure(claim, DeliveryErrorCategory.LEASE_EXPIRED, recovered_at):
                count += 1
        return count

    async def cleanup_delivered(self, cutoff: datetime, limit: int) -> int:
        async with serialized_write(self._write_lock):
            async with self._sessions.begin() as session:
                ids = (
                    await session.scalars(
                        select(OutboxEventRow.id)
                        .where(
                            OutboxEventRow.delivery_state == OutboxAggregateState.DELIVERED.value,
                            OutboxEventRow.delivered_at <= cutoff,
                        )
                        .limit(limit)
                    )
                ).all()
                if not ids:
                    return 0
                await session.execute(delete(OutboxEventRow).where(OutboxEventRow.id.in_(ids)))
                return len(ids)

    @staticmethod
    async def _refresh_aggregate(
        session: AsyncSession,
        event_id: int,
        now: datetime,
    ) -> None:
        counts = (
            await session.execute(
                select(
                    func.count(OutboxDeliveryRow.id),
                    func.sum(
                        (
                            OutboxDeliveryRow.delivery_state == OutboxDeliveryState.DELIVERED.value
                        ).cast(Integer)
                    ),
                    func.sum(
                        (
                            OutboxDeliveryRow.delivery_state
                            == OutboxDeliveryState.DEAD_LETTER.value
                        ).cast(Integer)
                    ),
                ).where(OutboxDeliveryRow.event_log_id == event_id)
            )
        ).one()
        total, delivered, dead = int(counts[0] or 0), int(counts[1] or 0), int(counts[2] or 0)
        if dead:
            state = OutboxAggregateState.DEAD_LETTER.value
            delivered_at = None
            dead_at = now
        elif total and delivered == total:
            state = OutboxAggregateState.DELIVERED.value
            delivered_at = now
            dead_at = None
        else:
            state = OutboxAggregateState.PENDING.value
            delivered_at = None
            dead_at = None
        await session.execute(
            update(OutboxEventRow)
            .where(OutboxEventRow.event_log_id == event_id)
            .values(
                delivery_state=state,
                delivered_at=delivered_at,
                dead_lettered_at=dead_at,
            )
        )
