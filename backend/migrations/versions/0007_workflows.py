"""Persist workflows, stage runs, rooms, immutable messages, and tasks."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from agent_platform.infrastructure.database.schema import (
    PROJECT_CONFLICT_DATABASE_REVISION,
    WORKFLOW_DATABASE_REVISION,
)

revision: str = WORKFLOW_DATABASE_REVISION
down_revision: str | None = PROJECT_CONFLICT_DATABASE_REVISION
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflows",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("project_id", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("current_stage", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.CheckConstraint("version > 0", name="ck_workflows_version_positive"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflows_project_updated", "workflows", ["project_id", "updated_at"])
    op.create_index("ix_workflows_project_status", "workflows", ["project_id", "status"])

    op.create_table(
        "stage_runs",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("workflow_id", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(20), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.CheckConstraint("attempt > 0", name="ck_stage_runs_attempt_positive"),
        sa.CheckConstraint("version > 0", name="ck_stage_runs_version_positive"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workflow_id",
            "stage",
            "attempt",
            name="uq_stage_runs_workflow_stage_attempt",
        ),
    )
    op.create_index(
        "ix_stage_runs_current",
        "stage_runs",
        ["workflow_id", "stage", "attempt"],
    )

    op.create_table(
        "rooms",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("workflow_id", sa.String(80), nullable=False),
        sa.Column("stage_run_id", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("next_sequence", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["stage_run_id"], ["stage_runs.id"], ondelete="CASCADE"),
        sa.CheckConstraint("next_sequence > 0", name="ck_rooms_next_sequence_positive"),
        sa.CheckConstraint("version > 0", name="ck_rooms_version_positive"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stage_run_id", name="uq_rooms_stage_run_id"),
    )
    op.create_index("ix_rooms_workflow_stage", "rooms", ["workflow_id", "stage"])

    op.create_table(
        "messages",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("room_id", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("author", sa.String(20), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("correction_of_id", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["correction_of_id"], ["messages.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("sequence > 0", name="ck_messages_sequence_positive"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_id", "sequence", name="uq_messages_room_sequence"),
    )
    op.create_index("ix_messages_room_sequence", "messages", ["room_id", "sequence"])

    op.create_table(
        "tasks",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("workflow_id", sa.String(80), nullable=False),
        sa.Column("stage_run_id", sa.String(80), nullable=False),
        sa.Column("room_id", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["stage_run_id"], ["stage_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="CASCADE"),
        sa.CheckConstraint("version > 0", name="ck_tasks_version_positive"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tasks_workflow_queue",
        "tasks",
        ["workflow_id", "status", "created_at"],
    )
    op.create_index("ix_tasks_room_created", "tasks", ["room_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_tasks_room_created", table_name="tasks")
    op.drop_index("ix_tasks_workflow_queue", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index("ix_messages_room_sequence", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_rooms_workflow_stage", table_name="rooms")
    op.drop_table("rooms")
    op.drop_index("ix_stage_runs_current", table_name="stage_runs")
    op.drop_table("stage_runs")
    op.drop_index("ix_workflows_project_status", table_name="workflows")
    op.drop_index("ix_workflows_project_updated", table_name="workflows")
    op.drop_table("workflows")
