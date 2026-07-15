from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
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


class WorkflowRow(Base):
    __tablename__ = "workflows"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_workflows_version_positive"),
        Index("ix_workflows_project_updated", "project_id", "updated_at"),
        Index("ix_workflows_project_status", "project_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    execution_mode: Mapped[str] = mapped_column(String(20), nullable=False, server_default="manual")
    current_stage: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class StageRunRow(Base):
    __tablename__ = "stage_runs"
    __table_args__ = (
        UniqueConstraint(
            "workflow_id",
            "stage",
            "attempt",
            name="uq_stage_runs_workflow_stage_attempt",
        ),
        CheckConstraint("attempt > 0", name="ck_stage_runs_attempt_positive"),
        CheckConstraint("version > 0", name="ck_stage_runs_version_positive"),
        Index("ix_stage_runs_current", "workflow_id", "stage", "attempt"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(20), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class RoomRow(Base):
    __tablename__ = "rooms"
    __table_args__ = (
        UniqueConstraint("stage_run_id", name="uq_rooms_stage_run_id"),
        CheckConstraint("next_sequence > 0", name="ck_rooms_next_sequence_positive"),
        CheckConstraint("version > 0", name="ck_rooms_version_positive"),
        Index("ix_rooms_workflow_stage", "workflow_id", "stage"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage_run_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("stage_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    next_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class MessageRow(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("room_id", "sequence", name="uq_messages_room_sequence"),
        CheckConstraint("sequence > 0", name="ck_messages_sequence_positive"),
        Index("ix_messages_room_sequence", "room_id", "sequence"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    room_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("rooms.id", ondelete="CASCADE"),
        nullable=False,
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    author: Mapped[str] = mapped_column(String(20), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    correction_of_id: Mapped[str | None] = mapped_column(
        String(80),
        ForeignKey("messages.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class WorkflowTaskRow(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_tasks_version_positive"),
        Index("ix_tasks_workflow_queue", "workflow_id", "status", "created_at"),
        Index("ix_tasks_room_created", "room_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage_run_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("stage_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    room_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("rooms.id", ondelete="CASCADE"),
        nullable=False,
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    result: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class ModelProfileRow(Base):
    __tablename__ = "model_profiles"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_model_profiles_version_positive"),
        Index("ix_model_profiles_provider_enabled", "provider", "enabled"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    base_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    credential_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    masked_hint: Mapped[str] = mapped_column(String(40), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class RoomModelAssignmentRow(Base):
    __tablename__ = "room_model_assignments"
    __table_args__ = (CheckConstraint("version > 0", name="ck_assignments_version_positive"),)

    room_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("rooms.id", ondelete="CASCADE"),
        primary_key=True,
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    primary_profile_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("model_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reviewer_a_profile_id: Mapped[str | None] = mapped_column(
        String(80),
        ForeignKey("model_profiles.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reviewer_b_profile_id: Mapped[str | None] = mapped_column(
        String(80),
        ForeignKey("model_profiles.id", ondelete="RESTRICT"),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class AgentRunRow(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        UniqueConstraint("room_id", "request_key", name="uq_agent_runs_room_request"),
        CheckConstraint("version > 0", name="ck_agent_runs_version_positive"),
        CheckConstraint(
            "final_output_bytes IS NULL OR final_output_bytes >= 0",
            name="ck_agent_runs_output_bytes_nonnegative",
        ),
        Index("ix_agent_runs_room_created", "room_id", "created_at"),
        Index("ix_agent_runs_workflow_status", "workflow_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
    )
    room_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("rooms.id", ondelete="CASCADE"),
        nullable=False,
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    request_key: Mapped[str] = mapped_column(String(128), nullable=False)
    formal: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    final_output_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    final_output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    final_output_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class ModelCallRow(Base):
    __tablename__ = "model_calls"
    __table_args__ = (
        UniqueConstraint(
            "agent_run_id",
            "role",
            "phase",
            name="uq_model_calls_run_role_phase",
        ),
        CheckConstraint("version > 0", name="ck_model_calls_version_positive"),
        CheckConstraint(
            "output_bytes IS NULL OR output_bytes >= 0",
            name="ck_model_calls_output_bytes_nonnegative",
        ),
        Index("ix_model_calls_run", "agent_run_id", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    agent_run_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    profile_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("model_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    phase: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    output_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class UsageRecordRow(Base):
    __tablename__ = "usage_records"
    __table_args__ = (
        CheckConstraint("input_tokens >= 0", name="ck_usage_input_nonnegative"),
        CheckConstraint("output_tokens >= 0", name="ck_usage_output_nonnegative"),
        CheckConstraint("total_tokens >= 0", name="ck_usage_total_nonnegative"),
        CheckConstraint(
            "total_tokens = input_tokens + output_tokens",
            name="ck_usage_total_matches",
        ),
    )

    model_call_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("model_calls.id", ondelete="CASCADE"),
        primary_key=True,
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ConversationSummaryRow(Base):
    __tablename__ = "conversation_summaries"
    __table_args__ = (
        UniqueConstraint(
            "room_id",
            "through_sequence",
            name="uq_summaries_room_sequence",
        ),
        CheckConstraint("through_sequence > 0", name="ck_summaries_sequence_positive"),
        Index("ix_summaries_room_latest", "room_id", "through_sequence"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    room_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("rooms.id", ondelete="CASCADE"),
        nullable=False,
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    through_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class CapabilityRequestRow(Base):
    __tablename__ = "capability_requests"
    __table_args__ = (
        UniqueConstraint("task_id", "idempotency_key", name="uq_capability_requests_task_key"),
        CheckConstraint("version > 0", name="ck_capability_requests_version_positive"),
        Index(
            "ix_capability_requests_workflow_status",
            "workflow_id",
            "status",
            "requested_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    workflow_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    stage_run_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("stage_runs.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(20), nullable=False)
    capability: Mapped[str] = mapped_column(String(120), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    target_paths: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    command: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ApprovalRow(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        UniqueConstraint("kind", "target_id", name="uq_approvals_kind_target"),
        CheckConstraint("version > 0", name="ck_approvals_version_positive"),
        Index("ix_approvals_workflow_status", "workflow_id", "status", "requested_at"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    workflow_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    target_id: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ToolCallRow(Base):
    __tablename__ = "tool_calls"
    __table_args__ = (
        UniqueConstraint("task_id", "idempotency_key", name="uq_tool_calls_task_key"),
        Index("ix_tool_calls_workflow_status", "workflow_id", "status", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    workflow_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    stage_run_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("stage_runs.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    capability_request_id: Mapped[str | None] = mapped_column(
        String(80), ForeignKey("capability_requests.id", ondelete="SET NULL"), nullable=True
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False)
    capability: Mapped[str] = mapped_column(String(120), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    arguments_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    result: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class ArtifactRow(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        UniqueConstraint("workflow_id", "stage", "name", name="uq_artifacts_workflow_stage_name"),
        UniqueConstraint("workflow_id", "relative_path", name="uq_artifacts_workflow_path"),
        Index("ix_artifacts_workflow_stage", "workflow_id", "stage"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    workflow_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ArtifactVersionRow(Base):
    __tablename__ = "artifact_versions"
    __table_args__ = (
        UniqueConstraint("artifact_id", "version", name="uq_artifact_versions_artifact_version"),
        CheckConstraint("version > 0", name="ck_artifact_versions_version_positive"),
        CheckConstraint("byte_size >= 0", name="ck_artifact_versions_size_nonnegative"),
        Index("ix_artifact_versions_stage_status", "stage_run_id", "status", "version"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False
    )
    stage_run_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("stage_runs.id", ondelete="CASCADE"), nullable=False
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    supersedes_id: Mapped[str | None] = mapped_column(
        String(80), ForeignKey("artifact_versions.id", ondelete="RESTRICT"), nullable=True
    )
    checkpoint_id: Mapped[str | None] = mapped_column(
        String(80), ForeignKey("project_checkpoints.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    locked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    invalidated_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    invalidation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class QualityGateRunRow(Base):
    __tablename__ = "quality_gate_runs"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_quality_gate_runs_version_positive"),
        Index("ix_quality_gate_runs_stage", "stage_run_id", "evaluated_at"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    workflow_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    stage_run_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("stage_runs.id", ondelete="CASCADE"), nullable=False
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    resolution: Mapped[str] = mapped_column(String(24), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class QualityGateIssueRow(Base):
    __tablename__ = "quality_gate_issues"
    __table_args__ = (
        UniqueConstraint("gate_run_id", "code", name="uq_quality_gate_issues_gate_code"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    gate_run_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("quality_gate_runs.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(120), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)


class QualityGateArtifactRow(Base):
    __tablename__ = "quality_gate_artifacts"

    gate_run_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("quality_gate_runs.id", ondelete="CASCADE"), primary_key=True
    )
    artifact_version_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("artifact_versions.id", ondelete="RESTRICT"), primary_key=True
    )


class HandoffPacketRow(Base):
    __tablename__ = "handoff_packets"
    __table_args__ = (
        UniqueConstraint("gate_run_id", name="uq_handoff_packets_gate"),
        Index("ix_handoff_packets_workflow_status", "workflow_id", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    workflow_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    from_stage_run_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("stage_runs.id", ondelete="CASCADE"), nullable=False
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    from_stage: Mapped[str] = mapped_column(String(20), nullable=False)
    to_stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    gate_run_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("quality_gate_runs.id", ondelete="RESTRICT"), nullable=False
    )
    checkpoint_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("project_checkpoints.id", ondelete="RESTRICT"), nullable=False
    )
    artifact_version_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    invalidated_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    invalidation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ChangeRequestRow(Base):
    __tablename__ = "change_requests"
    __table_args__ = (
        Index("ix_change_requests_workflow_status", "workflow_id", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    workflow_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    source_stage_run_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("stage_runs.id", ondelete="CASCADE"), nullable=False
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    target_stage: Mapped[str] = mapped_column(String(20), nullable=False)
    gate_run_id: Mapped[str | None] = mapped_column(
        String(80), ForeignKey("quality_gate_runs.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    input_artifact_version_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class RecoveryRecordRow(Base):
    __tablename__ = "recovery_records"
    __table_args__ = (
        CheckConstraint("interrupted_tasks >= 0", name="ck_recovery_tasks_nonnegative"),
        CheckConstraint("interrupted_agent_runs >= 0", name="ck_recovery_agent_runs_nonnegative"),
        CheckConstraint("interrupted_tool_calls >= 0", name="ck_recovery_tool_calls_nonnegative"),
        Index("ix_recovery_records_status", "status", "detected_at"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    workflow_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    stage_run_id: Mapped[str | None] = mapped_column(
        String(80), ForeignKey("stage_runs.id", ondelete="SET NULL"), nullable=True
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    interrupted_tasks: Mapped[int] = mapped_column(Integer, nullable=False)
    interrupted_agent_runs: Mapped[int] = mapped_column(Integer, nullable=False)
    interrupted_tool_calls: Mapped[int] = mapped_column(Integer, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
