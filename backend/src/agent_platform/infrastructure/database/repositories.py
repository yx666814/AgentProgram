from __future__ import annotations

import re
from copy import deepcopy
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from agent_platform.domain.events.models import ActorRef, ActorType, EventEnvelope, EventSource
from agent_platform.domain.events.outbox import OutboxAggregateState, OutboxDeliveryState
from agent_platform.domain.shared.ids import new_id
from agent_platform.infrastructure.database.models import (
    EventLogRow,
    OutboxDeliveryRow,
    OutboxEventRow,
)
from agent_platform.ports.event_publishing import LOCAL_AUDIT_CONSUMER

_CONSUMER_NAME = re.compile(r"[a-z][a-z0-9_]{0,79}\Z")
_AGGREGATE_TYPE = re.compile(r"[a-z][a-z0-9_]{0,79}\Z")


class EventLogRepository:
    def __init__(
        self,
        session: AsyncSession,
        delivery_targets: tuple[str, ...] = (LOCAL_AUDIT_CONSUMER,),
    ) -> None:
        if (
            not delivery_targets
            or len(set(delivery_targets)) != len(delivery_targets)
            or LOCAL_AUDIT_CONSUMER not in delivery_targets
            or any(_CONSUMER_NAME.fullmatch(target) is None for target in delivery_targets)
        ):
            raise ValueError("delivery targets are invalid")
        self._session = session
        self._delivery_targets = delivery_targets

    async def append(
        self,
        *,
        envelope: EventEnvelope,
        aggregate_type: str,
        aggregate_id: str,
    ) -> int:
        if envelope.event_id is not None:
            raise ValueError("new events must not provide event_id")
        if _AGGREGATE_TYPE.fullmatch(aggregate_type) is None:
            raise ValueError("aggregate type is invalid")
        if (
            not aggregate_id
            or len(aggregate_id) > 80
            or not aggregate_id.isascii()
            or not aggregate_id.isprintable()
        ):
            raise ValueError("aggregate id is invalid")
        event = EventLogRow(
            schema_version=envelope.schema_version,
            event_type=envelope.event_type,
            correlation_id=envelope.correlation_id,
            causation_id=envelope.causation_id,
            actor_type=envelope.actor.type.value,
            actor_id=envelope.actor.id,
            source=envelope.source.value,
            occurred_at=envelope.occurred_at,
            project_id=envelope.project_id,
            workflow_id=envelope.workflow_id,
            room_id=envelope.room_id,
            task_id=envelope.task_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=deepcopy(envelope.payload),
        )
        self._session.add(event)
        await self._session.flush()
        created_at = datetime.now(UTC)
        self._session.add(
            OutboxEventRow(
                id=new_id("out"),
                event_log_id=event.event_id,
                delivery_state=OutboxAggregateState.PENDING.value,
                created_at=created_at,
            )
        )
        await self._session.flush()
        for consumer_name in self._delivery_targets:
            self._session.add(
                OutboxDeliveryRow(
                    id=new_id("delivery"),
                    event_log_id=event.event_id,
                    consumer_name=consumer_name,
                    delivery_state=OutboxDeliveryState.PENDING.value,
                    next_attempt_at=created_at,
                    attempt_count=0,
                    created_at=created_at,
                )
            )
        await self._session.flush()
        return event.event_id

    async def get(self, event_id: int) -> EventEnvelope | None:
        row = await self._session.get(EventLogRow, event_id)
        if row is None:
            return None
        if row.schema_version != 1:
            raise ValueError("persisted event schema version is invalid")
        return EventEnvelope(
            schema_version=1,
            event_id=row.event_id,
            event_type=row.event_type,
            correlation_id=row.correlation_id,
            causation_id=row.causation_id,
            actor=ActorRef(type=ActorType(row.actor_type), id=row.actor_id),
            source=EventSource(row.source),
            occurred_at=row.occurred_at,
            project_id=row.project_id,
            workflow_id=row.workflow_id,
            room_id=row.room_id,
            task_id=row.task_id,
            payload=deepcopy(row.payload),
        )
