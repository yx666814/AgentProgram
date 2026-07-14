"""Persist complete event envelopes and reliable outbox targets."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from agent_platform.infrastructure.database.schema import (
    FOUNDATION_DATABASE_REVISION,
    RELIABLE_OUTBOX_DATABASE_REVISION,
)

revision: str = RELIABLE_OUTBOX_DATABASE_REVISION
down_revision: str | None = FOUNDATION_DATABASE_REVISION
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("PRAGMA foreign_keys=OFF")
    op.rename_table("event_log", "event_log_legacy")
    op.rename_table("outbox_events", "outbox_events_legacy")
    for index_name in (
        "ix_event_log_aggregate_id",
        "ix_event_log_event_type",
        "ix_event_log_project_id",
        "ix_event_log_room_id",
        "ix_event_log_task_id",
        "ix_event_log_workflow_id",
    ):
        op.drop_index(index_name, table_name="event_log_legacy")
    op.drop_index("ix_outbox_events_delivery_state", table_name="outbox_events_legacy")

    op.create_table(
        "event_log",
        sa.Column("event_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("correlation_id", sa.String(120), nullable=False),
        sa.Column("causation_id", sa.String(120), nullable=True),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("actor_id", sa.String(80), nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("project_id", sa.String(80), nullable=True),
        sa.Column("workflow_id", sa.String(80), nullable=True),
        sa.Column("room_id", sa.String(80), nullable=True),
        sa.Column("task_id", sa.String(80), nullable=True),
        sa.Column("aggregate_type", sa.String(80), nullable=False),
        sa.Column("aggregate_id", sa.String(80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.CheckConstraint("schema_version = 1", name="ck_event_log_schema_version"),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("ix_event_log_event_type", "event_log", ["event_type"])
    op.create_index("ix_event_log_project_id", "event_log", ["project_id"])
    op.create_index("ix_event_log_workflow_id", "event_log", ["workflow_id"])
    op.create_index("ix_event_log_room_id", "event_log", ["room_id"])
    op.create_index("ix_event_log_task_id", "event_log", ["task_id"])
    op.create_index("ix_event_log_aggregate_id", "event_log", ["aggregate_id"])

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("event_log_id", sa.Integer(), nullable=False),
        sa.Column("delivery_state", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("dead_lettered_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["event_log_id"], ["event_log.event_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_log_id", name="uq_outbox_events_event_log_id"),
    )
    op.create_index("ix_outbox_events_delivery_state", "outbox_events", ["delivery_state"])
    op.create_table(
        "outbox_deliveries",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("event_log_id", sa.Integer(), nullable=False),
        sa.Column("consumer_name", sa.String(80), nullable=False),
        sa.Column("delivery_state", sa.String(20), nullable=False),
        sa.Column("lease_owner", sa.String(80), nullable=True),
        sa.Column("lease_token", sa.String(80), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_error_category", sa.String(40), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("dead_lettered_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["event_log_id"], ["outbox_events.event_log_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_log_id", "consumer_name", name="uq_outbox_delivery_event_consumer"
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_outbox_delivery_attempt_nonnegative"),
    )
    op.create_index(
        "ix_outbox_delivery_eligibility",
        "outbox_deliveries",
        ["delivery_state", "next_attempt_at", "lease_expires_at"],
    )
    op.create_table(
        "local_audit_events",
        sa.Column("event_log_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("correlation_id", sa.String(120), nullable=False),
        sa.Column("causation_id", sa.String(120), nullable=True),
        sa.Column("project_id", sa.String(80), nullable=True),
        sa.Column("workflow_id", sa.String(80), nullable=True),
        sa.Column("room_id", sa.String(80), nullable=True),
        sa.Column("task_id", sa.String(80), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["event_log_id"], ["event_log.event_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_log_id"),
    )

    op.execute(
        """
        INSERT INTO event_log (
            event_id, schema_version, event_type, correlation_id, causation_id,
            actor_type, actor_id, source, occurred_at, project_id, workflow_id,
            room_id, task_id, aggregate_type, aggregate_id, payload
        )
        SELECT event_id, 1, event_type, 'legacy:event:' || event_id, NULL,
               'system', NULL, 'backend', created_at, project_id, workflow_id,
               room_id, task_id, aggregate_type, aggregate_id, payload
        FROM event_log_legacy
        """
    )
    op.execute(
        """
        INSERT INTO outbox_events (id, event_log_id, delivery_state, created_at)
        SELECT id, event_log_id, 'pending', created_at FROM outbox_events_legacy
        """
    )
    op.execute(
        """
        INSERT INTO outbox_events (id, event_log_id, delivery_state, created_at)
        SELECT 'out_legacy_' || e.event_id, e.event_id, 'pending', e.occurred_at
        FROM event_log e LEFT JOIN outbox_events o ON o.event_log_id = e.event_id
        WHERE o.event_log_id IS NULL
        """
    )
    op.execute(
        """
        INSERT INTO outbox_deliveries (
            id, event_log_id, consumer_name, delivery_state,
            next_attempt_at, attempt_count, created_at
        )
        SELECT 'delivery_legacy_' || event_log_id, event_log_id, 'local_audit_v1',
               'pending', created_at, 0, created_at
        FROM outbox_events
        """
    )
    op.drop_table("outbox_events_legacy")
    op.drop_table("event_log_legacy")
    op.execute("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    op.execute("PRAGMA foreign_keys=OFF")
    op.rename_table("event_log", "event_log_stage1h")
    op.rename_table("outbox_events", "outbox_events_stage1h")
    for index_name in (
        "ix_event_log_aggregate_id",
        "ix_event_log_event_type",
        "ix_event_log_project_id",
        "ix_event_log_room_id",
        "ix_event_log_task_id",
        "ix_event_log_workflow_id",
    ):
        op.drop_index(index_name, table_name="event_log_stage1h")
    op.drop_index("ix_outbox_events_delivery_state", table_name="outbox_events_stage1h")
    op.drop_table("local_audit_events")
    op.drop_table("outbox_deliveries")

    op.create_table(
        "event_log",
        sa.Column("event_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("project_id", sa.String(80), nullable=True),
        sa.Column("workflow_id", sa.String(80), nullable=True),
        sa.Column("room_id", sa.String(80), nullable=True),
        sa.Column("task_id", sa.String(80), nullable=True),
        sa.Column("aggregate_type", sa.String(80), nullable=False),
        sa.Column("aggregate_id", sa.String(80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("ix_event_log_aggregate_id", "event_log", ["aggregate_id"])
    op.create_index("ix_event_log_event_type", "event_log", ["event_type"])
    op.create_index("ix_event_log_project_id", "event_log", ["project_id"])
    op.create_index("ix_event_log_room_id", "event_log", ["room_id"])
    op.create_index("ix_event_log_task_id", "event_log", ["task_id"])
    op.create_index("ix_event_log_workflow_id", "event_log", ["workflow_id"])
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("event_log_id", sa.Integer(), nullable=False),
        sa.Column("delivery_state", sa.String(20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["event_log_id"], ["event_log.event_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_log_id", name="uq_outbox_events_event_log_id"),
    )
    op.create_index("ix_outbox_events_delivery_state", "outbox_events", ["delivery_state"])
    op.execute(
        """
        INSERT INTO event_log (
            event_id, event_type, project_id, workflow_id, room_id, task_id,
            aggregate_type, aggregate_id, payload, created_at
        )
        SELECT event_id, event_type, project_id, workflow_id, room_id, task_id,
               aggregate_type, aggregate_id, payload, occurred_at
        FROM event_log_stage1h
        """
    )
    op.execute(
        """
        INSERT INTO outbox_events (
            id, event_log_id, delivery_state, attempt_count, created_at,
            last_attempt_at, delivered_at
        )
        SELECT id, event_log_id, delivery_state, 0, created_at, NULL, delivered_at
        FROM outbox_events_stage1h
        """
    )
    op.drop_table("outbox_events_stage1h")
    op.drop_table("event_log_stage1h")
    op.execute("PRAGMA foreign_keys=ON")
