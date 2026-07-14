from __future__ import annotations

from datetime import timedelta
from enum import StrEnum


class OutboxAggregateState(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    DEAD_LETTER = "dead_letter"


class OutboxDeliveryState(StrEnum):
    PENDING = "pending"
    LEASED = "leased"
    RETRY_WAIT = "retry_wait"
    DELIVERED = "delivered"
    DEAD_LETTER = "dead_letter"


class DeliveryErrorCategory(StrEnum):
    LEASE_EXPIRED = "lease_expired"
    PUBLISHER_UNAVAILABLE = "publisher_unavailable"
    PUBLISHER_TIMEOUT = "publisher_timeout"
    PUBLISHER_FAILURE = "publisher_failure"


def retry_delay(attempt_count: int, *, base_seconds: float, maximum_seconds: float) -> timedelta:
    if attempt_count < 1:
        raise ValueError("attempt_count must be positive")
    return timedelta(seconds=min(maximum_seconds, base_seconds * (2 ** (attempt_count - 1))))
