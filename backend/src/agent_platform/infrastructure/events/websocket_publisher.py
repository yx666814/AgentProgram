from __future__ import annotations

from datetime import datetime

from agent_platform.application.events import EventStreamBroker
from agent_platform.domain.events import EventEnvelope
from agent_platform.ports.event_publishing import WEBSOCKET_CONSUMER


class WebSocketEventPublisher:
    def __init__(self, broker: EventStreamBroker) -> None:
        self._broker = broker

    @property
    def consumer_name(self) -> str:
        return WEBSOCKET_CONSUMER

    async def publish(
        self,
        envelope: EventEnvelope,
        *,
        idempotency_key: int,
        delivery_id: str,
        lease_token: str,
        delivered_at: datetime,
    ) -> None:
        del delivery_id, lease_token, delivered_at
        await self._broker.publish(envelope, event_id=idempotency_key)
