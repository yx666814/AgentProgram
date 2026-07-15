"""Persist model profiles, assignments, agent runs, calls, usage, and summaries."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from agent_platform.infrastructure.database.schema import (
    MODEL_RUNTIME_DATABASE_REVISION,
    WORKFLOW_DATABASE_REVISION,
)

revision: str = MODEL_RUNTIME_DATABASE_REVISION
down_revision: str | None = WORKFLOW_DATABASE_REVISION
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_profiles",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("base_url", sa.String(2048), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("credential_ref", sa.String(128), nullable=False),
        sa.Column("masked_hint", sa.String(40), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_model_profiles_version_positive"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_model_profiles_provider_enabled",
        "model_profiles",
        ["provider", "enabled"],
    )
    op.create_table(
        "room_model_assignments",
        sa.Column("room_id", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("primary_profile_id", sa.String(80), nullable=False),
        sa.Column("reviewer_a_profile_id", sa.String(80), nullable=True),
        sa.Column("reviewer_b_profile_id", sa.String(80), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["primary_profile_id"], ["model_profiles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["reviewer_a_profile_id"], ["model_profiles.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_b_profile_id"], ["model_profiles.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint("version > 0", name="ck_assignments_version_positive"),
        sa.PrimaryKeyConstraint("room_id"),
    )
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("workflow_id", sa.String(80), nullable=False),
        sa.Column("room_id", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("formal", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("final_output_ref", sa.String(500), nullable=True),
        sa.Column("final_output_hash", sa.String(64), nullable=True),
        sa.Column("final_output_bytes", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(120), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="CASCADE"),
        sa.CheckConstraint("version > 0", name="ck_agent_runs_version_positive"),
        sa.CheckConstraint(
            "final_output_bytes IS NULL OR final_output_bytes >= 0",
            name="ck_agent_runs_output_bytes_nonnegative",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_id", "request_key", name="uq_agent_runs_room_request"),
    )
    op.create_index("ix_agent_runs_room_created", "agent_runs", ["room_id", "created_at"])
    op.create_index("ix_agent_runs_workflow_status", "agent_runs", ["workflow_id", "status"])
    op.create_table(
        "model_calls",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("agent_run_id", sa.String(80), nullable=False),
        sa.Column("profile_id", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("phase", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("output_ref", sa.String(500), nullable=True),
        sa.Column("output_hash", sa.String(64), nullable=True),
        sa.Column("output_bytes", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(120), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["model_profiles.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("version > 0", name="ck_model_calls_version_positive"),
        sa.CheckConstraint(
            "output_bytes IS NULL OR output_bytes >= 0",
            name="ck_model_calls_output_bytes_nonnegative",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "agent_run_id",
            "role",
            "phase",
            name="uq_model_calls_run_role_phase",
        ),
    )
    op.create_index("ix_model_calls_run", "model_calls", ["agent_run_id", "started_at"])
    op.create_table(
        "usage_records",
        sa.Column("model_call_id", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["model_call_id"], ["model_calls.id"], ondelete="CASCADE"),
        sa.CheckConstraint("input_tokens >= 0", name="ck_usage_input_nonnegative"),
        sa.CheckConstraint("output_tokens >= 0", name="ck_usage_output_nonnegative"),
        sa.CheckConstraint("total_tokens >= 0", name="ck_usage_total_nonnegative"),
        sa.CheckConstraint(
            "total_tokens = input_tokens + output_tokens",
            name="ck_usage_total_matches",
        ),
        sa.PrimaryKeyConstraint("model_call_id"),
    )
    op.create_table(
        "conversation_summaries",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("room_id", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("through_sequence", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="CASCADE"),
        sa.CheckConstraint("through_sequence > 0", name="ck_summaries_sequence_positive"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "room_id",
            "through_sequence",
            name="uq_summaries_room_sequence",
        ),
    )
    op.create_index(
        "ix_summaries_room_latest",
        "conversation_summaries",
        ["room_id", "through_sequence"],
    )


def downgrade() -> None:
    op.drop_index("ix_summaries_room_latest", table_name="conversation_summaries")
    op.drop_table("conversation_summaries")
    op.drop_table("usage_records")
    op.drop_index("ix_model_calls_run", table_name="model_calls")
    op.drop_table("model_calls")
    op.drop_index("ix_agent_runs_workflow_status", table_name="agent_runs")
    op.drop_index("ix_agent_runs_room_created", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_table("room_model_assignments")
    op.drop_index("ix_model_profiles_provider_enabled", table_name="model_profiles")
    op.drop_table("model_profiles")
