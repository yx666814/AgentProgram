from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import OperationalError

from agent_platform.domain.events.outbox import DeliveryErrorCategory
from agent_platform.infrastructure.database.outbox_store import SqlAlchemyOutboxStore
from agent_platform.ports.event_publishing import EventPublisher


class OutboxDispatcher:
    def __init__(
        self,
        *,
        store: SqlAlchemyOutboxStore,
        publishers: tuple[EventPublisher, ...],
        poll_interval_seconds: float,
        publish_timeout_seconds: float,
        cleanup_interval_seconds: float,
        delivered_retention: timedelta,
        cleanup_batch_size: int,
    ) -> None:
        registry = {publisher.consumer_name: publisher for publisher in publishers}
        if len(registry) != len(publishers):
            raise ValueError("duplicate Outbox publisher")
        self._store = store
        self._publishers = registry
        self._poll_interval = poll_interval_seconds
        self._publish_timeout = publish_timeout_seconds
        self._cleanup_interval = cleanup_interval_seconds
        self._delivered_retention = delivered_retention
        self._cleanup_batch_size = cleanup_batch_size
        self._stop = asyncio.Event()

    def request_stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        next_cleanup = loop.time() + self._cleanup_interval
        recovery_due = True
        while not self._stop.is_set():
            try:
                now = datetime.now(UTC)
                if recovery_due:
                    await self._store.recover_expired_leases(now)
                    recovery_due = False
                if loop.time() >= next_cleanup:
                    await self._store.recover_expired_leases(now)
                    await self._store.cleanup_delivered(
                        now - self._delivered_retention,
                        self._cleanup_batch_size,
                    )
                    next_cleanup = loop.time() + self._cleanup_interval
                claim = await self._store.claim_next(now)
            except OperationalError:
                claim = None
            if claim is None:
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self._poll_interval)
                except TimeoutError:
                    pass
                continue
            publisher = self._publishers.get(claim.consumer_name)
            if publisher is None:
                await self._store.record_failure(
                    claim,
                    DeliveryErrorCategory.PUBLISHER_UNAVAILABLE,
                    datetime.now(UTC),
                )
                continue
            try:
                async with asyncio.timeout(self._publish_timeout):
                    await publisher.publish(
                        claim.envelope,
                        idempotency_key=claim.event_id,
                        delivery_id=claim.delivery_id,
                        lease_token=claim.lease_token,
                        delivered_at=datetime.now(UTC),
                    )
            except TimeoutError:
                await self._store.record_failure(
                    claim,
                    DeliveryErrorCategory.PUBLISHER_TIMEOUT,
                    datetime.now(UTC),
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                await self._store.record_failure(
                    claim,
                    DeliveryErrorCategory.PUBLISHER_FAILURE,
                    datetime.now(UTC),
                )
