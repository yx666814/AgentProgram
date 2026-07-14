from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol

from agent_platform.domain.events.models import EventEnvelope

LOCAL_AUDIT_CONSUMER: Final[str] = "local_audit_v1"


@dataclass(frozen=True, slots=True)
class ClaimedDelivery:
    delivery_id: str
    event_id: int
    consumer_name: str
    lease_token: str
    attempt_count: int
    envelope: EventEnvelope


class EventPublisher(Protocol):
    @property
    def consumer_name(self) -> str: ...

    async def publish(
        self,
        envelope: EventEnvelope,
        *,
        idempotency_key: int,
        delivery_id: str,
        lease_token: str,
        delivered_at: datetime,
    ) -> None: ...
