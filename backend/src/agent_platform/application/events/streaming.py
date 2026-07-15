from __future__ import annotations

import asyncio
import hashlib
import secrets
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from agent_platform.domain.events import EventEnvelope
from agent_platform.domain.shared.errors import DomainError, ErrorCategory
from agent_platform.domain.shared.ids import new_id
from agent_platform.infrastructure.database.session import Database
from agent_platform.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork


@dataclass(frozen=True, slots=True)
class IssuedEventTicket:
    ticket: str
    workflow_id: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ConsumedEventTicket:
    workflow_id: str


@dataclass(frozen=True, slots=True)
class EventSubscription:
    id: str
    workflow_id: str
    queue: asyncio.Queue[EventEnvelope | None]


class EventTicketStore:
    def __init__(self, ttl: timedelta, *, max_pending: int = 1024) -> None:
        if ttl.total_seconds() <= 0 or max_pending < 1:
            raise ValueError("ticket store limits must be positive")
        self._ttl = ttl
        self._max_pending = max_pending
        self._tickets: OrderedDict[str, tuple[str, datetime]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def issue(self, workflow_id: str) -> IssuedEventTicket:
        token = secrets.token_urlsafe(32)
        digest = _ticket_digest(token)
        now = datetime.now(UTC)
        expires_at = now + self._ttl
        async with self._lock:
            self._prune(now)
            while len(self._tickets) >= self._max_pending:
                self._tickets.popitem(last=False)
            self._tickets[digest] = (workflow_id, expires_at)
        return IssuedEventTicket(ticket=token, workflow_id=workflow_id, expires_at=expires_at)

    async def consume(self, token: str) -> ConsumedEventTicket | None:
        if not token or len(token) > 256:
            return None
        digest = _ticket_digest(token)
        now = datetime.now(UTC)
        async with self._lock:
            self._prune(now)
            entry = self._tickets.pop(digest, None)
        if entry is None:
            return None
        workflow_id, expires_at = entry
        if expires_at <= now:
            return None
        return ConsumedEventTicket(workflow_id=workflow_id)

    def _prune(self, now: datetime) -> None:
        expired = [digest for digest, (_, expires_at) in self._tickets.items() if expires_at <= now]
        for digest in expired:
            self._tickets.pop(digest, None)


class EventStreamBroker:
    def __init__(self, *, queue_capacity: int = 256, dedup_capacity: int = 4096) -> None:
        if queue_capacity < 1 or dedup_capacity < 1:
            raise ValueError("event stream capacities must be positive")
        self._queue_capacity = queue_capacity
        self._dedup_capacity = dedup_capacity
        self._subscriptions: dict[str, EventSubscription] = {}
        self._published: OrderedDict[int, None] = OrderedDict()
        self._lock = asyncio.Lock()

    async def subscribe(self, workflow_id: str) -> EventSubscription:
        subscription = EventSubscription(
            id=new_id("subscription"),
            workflow_id=workflow_id,
            queue=asyncio.Queue(maxsize=self._queue_capacity),
        )
        async with self._lock:
            self._subscriptions[subscription.id] = subscription
        return subscription

    async def unsubscribe(self, subscription_id: str) -> None:
        async with self._lock:
            self._subscriptions.pop(subscription_id, None)

    async def publish(self, envelope: EventEnvelope, *, event_id: int) -> None:
        if envelope.event_id != event_id:
            raise ValueError("published event id is inconsistent")
        async with self._lock:
            if event_id in self._published:
                return
            self._published[event_id] = None
            while len(self._published) > self._dedup_capacity:
                self._published.popitem(last=False)
            subscriptions = tuple(self._subscriptions.values())
            overflowed: list[str] = []
            for subscription in subscriptions:
                if subscription.workflow_id != envelope.workflow_id:
                    continue
                try:
                    subscription.queue.put_nowait(envelope)
                except asyncio.QueueFull:
                    overflowed.append(subscription.id)
                    while not subscription.queue.empty():
                        subscription.queue.get_nowait()
                    subscription.queue.put_nowait(None)
            for subscription_id in overflowed:
                self._subscriptions.pop(subscription_id, None)


class EventStreamService:
    def __init__(
        self,
        database: Database,
        ticket_store: EventTicketStore,
        broker: EventStreamBroker,
        *,
        replay_batch_size: int,
    ) -> None:
        if replay_batch_size < 1:
            raise ValueError("replay batch size must be positive")
        self._database = database
        self._ticket_store = ticket_store
        self._broker = broker
        self.replay_batch_size = replay_batch_size

    async def issue_ticket(self, workflow_id: str) -> IssuedEventTicket:
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            workflow = await uow.workflows.get(workflow_id)
        if workflow is None:
            raise DomainError(
                code="workflow.not_found",
                message="Workflow was not found",
                category=ErrorCategory.NOT_FOUND,
            )
        return await self._ticket_store.issue(workflow_id)

    async def consume_ticket(self, token: str) -> ConsumedEventTicket | None:
        return await self._ticket_store.consume(token)

    async def subscribe(self, workflow_id: str) -> EventSubscription:
        return await self._broker.subscribe(workflow_id)

    async def unsubscribe(self, subscription_id: str) -> None:
        await self._broker.unsubscribe(subscription_id)

    async def replay(
        self,
        workflow_id: str,
        *,
        after_event_id: int,
    ) -> tuple[EventEnvelope, ...]:
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            return await uow.events.list_after(
                after_event_id,
                workflow_id=workflow_id,
                limit=self.replay_batch_size,
            )


def _ticket_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
