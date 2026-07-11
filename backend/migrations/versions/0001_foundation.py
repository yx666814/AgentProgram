"""Create the foundation event log and outbox tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "event_log",
        sa.Column("event_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=True),
        sa.Column("workflow_id", sa.String(length=80), nullable=True),
        sa.Column("room_id", sa.String(length=80), nullable=True),
        sa.Column("task_id", sa.String(length=80), nullable=True),
        sa.Column("aggregate_type", sa.String(length=80), nullable=False),
        sa.Column("aggregate_id", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("ix_event_log_aggregate_id", "event_log", ["aggregate_id"], unique=False)
    op.create_index("ix_event_log_event_type", "event_log", ["event_type"], unique=False)
    op.create_index("ix_event_log_project_id", "event_log", ["project_id"], unique=False)
    op.create_index("ix_event_log_room_id", "event_log", ["room_id"], unique=False)
    op.create_index("ix_event_log_task_id", "event_log", ["task_id"], unique=False)
    op.create_index("ix_event_log_workflow_id", "event_log", ["workflow_id"], unique=False)

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("event_log_id", sa.Integer(), nullable=False),
        sa.Column(
            "delivery_state",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["event_log_id"],
            ["event_log.event_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_log_id", name="uq_outbox_events_event_log_id"),
    )
    op.create_index(
        "ix_outbox_events_delivery_state",
        "outbox_events",
        ["delivery_state"],
        unique=False,
    )
    op.create_index(
        "ix_outbox_events_event_log_id",
        "outbox_events",
        ["event_log_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_events_event_log_id", table_name="outbox_events")
    op.drop_index("ix_outbox_events_delivery_state", table_name="outbox_events")
    op.drop_index("ix_event_log_workflow_id", table_name="event_log")
    op.drop_index("ix_event_log_task_id", table_name="event_log")
    op.drop_index("ix_event_log_room_id", table_name="event_log")
    op.drop_index("ix_event_log_project_id", table_name="event_log")
    op.drop_index("ix_event_log_event_type", table_name="event_log")
    op.drop_index("ix_event_log_aggregate_id", table_name="event_log")
    op.drop_table("outbox_events")
    op.drop_table("event_log")
