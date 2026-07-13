from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from agent_platform.domain.shared.ids import new_id
from agent_platform.infrastructure.database.models import EventLogRow, OutboxEventRow


class EventLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, object],
        occurred_at: datetime,
        project_id: str | None = None,
        workflow_id: str | None = None,
        room_id: str | None = None,
        task_id: str | None = None,
    ) -> int:
        event = EventLogRow(
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload,
            created_at=occurred_at,
            project_id=project_id,
            workflow_id=workflow_id,
            room_id=room_id,
            task_id=task_id,
        )
        self._session.add(event)
        await self._session.flush()
        return event.event_id


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(self, event_id: int) -> str:
        outbox_id = new_id("out")
        event = OutboxEventRow(
            id=outbox_id,
            event_log_id=event_id,
            delivery_state="pending",
            attempt_count=0,
            created_at=datetime.now(UTC),
            last_attempt_at=None,
            delivered_at=None,
        )
        self._session.add(event)
        await self._session.flush()
        return outbox_id
