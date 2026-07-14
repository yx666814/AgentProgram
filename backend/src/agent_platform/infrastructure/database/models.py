from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from agent_platform.infrastructure.database.base import Base
from agent_platform.infrastructure.database.types import UTCDateTime


class EventLogRow(Base):
    __tablename__ = "event_log"
    __table_args__ = (
        CheckConstraint("schema_version = 1", name="ck_event_log_schema_version"),
        Index("ix_event_log_event_type", "event_type"),
        Index("ix_event_log_project_id", "project_id"),
        Index("ix_event_log_workflow_id", "workflow_id"),
        Index("ix_event_log_room_id", "room_id"),
        Index("ix_event_log_task_id", "task_id"),
        Index("ix_event_log_aggregate_id", "aggregate_id"),
    )

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(120), nullable=False)
    causation_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    project_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    workflow_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    room_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)


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
    delivery_state: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    dead_lettered_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class OutboxDeliveryRow(Base):
    __tablename__ = "outbox_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "event_log_id",
            "consumer_name",
            name="uq_outbox_delivery_event_consumer",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_outbox_delivery_attempt_nonnegative"),
        Index(
            "ix_outbox_delivery_eligibility",
            "delivery_state",
            "next_attempt_at",
            "lease_expires_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    event_log_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("outbox_events.event_log_id", ondelete="CASCADE"),
        nullable=False,
    )
    consumer_name: Mapped[str] = mapped_column(String(80), nullable=False)
    delivery_state: Mapped[str] = mapped_column(String(20), nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(80), nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(80), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    next_attempt_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    dead_lettered_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class LocalAuditEventRow(Base):
    __tablename__ = "local_audit_events"

    event_log_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("event_log.event_id", ondelete="CASCADE"),
        primary_key=True,
    )
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(120), nullable=False)
    causation_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    workflow_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    room_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    delivered_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
