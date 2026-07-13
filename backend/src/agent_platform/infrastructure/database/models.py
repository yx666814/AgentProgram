from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from agent_platform.infrastructure.database.base import Base
from agent_platform.infrastructure.database.types import UTCDateTime


class EventLogRow(Base):
    __tablename__ = "event_log"
    __table_args__ = (
        Index("ix_event_log_event_type", "event_type"),
        Index("ix_event_log_project_id", "project_id"),
        Index("ix_event_log_workflow_id", "workflow_id"),
        Index("ix_event_log_room_id", "room_id"),
        Index("ix_event_log_task_id", "task_id"),
        Index("ix_event_log_aggregate_id", "aggregate_id"),
    )

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    project_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    workflow_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    room_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class OutboxEventRow(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        UniqueConstraint("event_log_id", name="uq_outbox_events_event_log_id"),
        Index("ix_outbox_events_delivery_state", "delivery_state"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    event_log_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("event_log.event_id", ondelete="CASCADE"),
        nullable=False,
    )
    delivery_state: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(),
        nullable=True,
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(),
        nullable=True,
    )
