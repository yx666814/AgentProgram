from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
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


class ProjectRow(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_projects_version_positive"),
        Index("ix_projects_updated_at", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class WorkspaceRow(Base):
    __tablename__ = "workspaces"
    __table_args__ = (
        UniqueConstraint("project_id", name="uq_workspaces_project_id"),
        UniqueConstraint("canonical_root_path", name="uq_workspaces_canonical_root_path"),
        Index("ix_workspaces_mode", "mode"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    root_path: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_root_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ProjectManifestRow(Base):
    __tablename__ = "project_manifests"

    project_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest_version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    document: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ProjectInstructionRow(Base):
    __tablename__ = "project_instructions"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "relative_path",
            name="uq_project_instructions_project_path",
        ),
        Index("ix_project_instructions_project_id", "project_id"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ProjectPreflightRow(Base):
    __tablename__ = "project_preflight_runs"
    __table_args__ = (
        Index(
            "ix_project_preflight_runs_latest",
            "project_id",
            "completed_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    checks: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ProjectCheckpointRow(Base):
    __tablename__ = "project_checkpoints"
    __table_args__ = (
        CheckConstraint("file_count >= 0", name="ck_project_checkpoints_file_count"),
        CheckConstraint("total_bytes >= 0", name="ck_project_checkpoints_total_bytes"),
        Index("ix_project_checkpoints_latest", "project_id", "created_at"),
        Index("ix_project_checkpoints_content_hash", "content_hash"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest_version: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(20), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    file_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class CheckpointFileRow(Base):
    __tablename__ = "checkpoint_files"
    __table_args__ = (
        CheckConstraint("byte_size >= 0", name="ck_checkpoint_files_byte_size"),
        Index("ix_checkpoint_files_content_hash", "content_hash"),
    )

    checkpoint_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("project_checkpoints.id", ondelete="CASCADE"),
        primary_key=True,
    )
    relative_path: Mapped[str] = mapped_column(Text, primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)


class ExternalChangeRow(Base):
    __tablename__ = "external_changes"
    __table_args__ = (Index("ix_external_changes_open", "project_id", "status", "detected_at"),)

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    change_type: Mapped[str] = mapped_column(String(20), nullable=False)
    baseline_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class FileConflictRow(Base):
    __tablename__ = "file_conflicts"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_file_conflicts_version_positive"),
        Index("ix_file_conflicts_open", "project_id", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    baseline_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    resolution: Mapped[str | None] = mapped_column(String(20), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
