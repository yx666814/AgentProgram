"""Persist Stage 5 tooling, gates, handoffs, approvals, and recovery state."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from agent_platform.infrastructure.database.schema import (
    MODEL_RUNTIME_DATABASE_REVISION,
    STAGE5_DATABASE_REVISION,
)

revision: str = STAGE5_DATABASE_REVISION
down_revision: str | None = MODEL_RUNTIME_DATABASE_REVISION
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workflows",
        sa.Column(
            "execution_mode",
            sa.String(20),
            nullable=False,
            server_default="manual",
        ),
    )

    op.create_table(
        "capability_requests",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("project_id", sa.String(80), nullable=False),
        sa.Column("workflow_id", sa.String(80), nullable=False),
        sa.Column("stage_run_id", sa.String(80), nullable=False),
        sa.Column("task_id", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(20), nullable=False),
        sa.Column("capability", sa.String(120), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("target_paths", sa.JSON(), nullable=False),
        sa.Column("command", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("risk_level", sa.String(20), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["stage_run_id"], ["stage_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.CheckConstraint("version > 0", name="ck_capability_requests_version_positive"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "task_id",
            "idempotency_key",
            name="uq_capability_requests_task_key",
        ),
    )
    op.create_index(
        "ix_capability_requests_workflow_status",
        "capability_requests",
        ["workflow_id", "status", "requested_at"],
    )

    op.create_table(
        "approvals",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("project_id", sa.String(80), nullable=False),
        sa.Column("workflow_id", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("target_id", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.CheckConstraint("version > 0", name="ck_approvals_version_positive"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "target_id", name="uq_approvals_kind_target"),
    )
    op.create_index(
        "ix_approvals_workflow_status",
        "approvals",
        ["workflow_id", "status", "requested_at"],
    )

    op.create_table(
        "tool_calls",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("project_id", sa.String(80), nullable=False),
        sa.Column("workflow_id", sa.String(80), nullable=False),
        sa.Column("stage_run_id", sa.String(80), nullable=False),
        sa.Column("task_id", sa.String(80), nullable=False),
        sa.Column("capability_request_id", sa.String(80), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(120), nullable=False),
        sa.Column("capability", sa.String(120), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("arguments_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(120), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["stage_run_id"], ["stage_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["capability_request_id"], ["capability_requests.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "idempotency_key", name="uq_tool_calls_task_key"),
    )
    op.create_index(
        "ix_tool_calls_workflow_status",
        "tool_calls",
        ["workflow_id", "status", "started_at"],
    )

    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("project_id", sa.String(80), nullable=False),
        sa.Column("workflow_id", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(20), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workflow_id",
            "stage",
            "name",
            name="uq_artifacts_workflow_stage_name",
        ),
        sa.UniqueConstraint(
            "workflow_id",
            "relative_path",
            name="uq_artifacts_workflow_path",
        ),
    )
    op.create_index("ix_artifacts_workflow_stage", "artifacts", ["workflow_id", "stage"])

    op.create_table(
        "artifact_versions",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("artifact_id", sa.String(80), nullable=False),
        sa.Column("stage_run_id", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("supersedes_id", sa.String(80), nullable=True),
        sa.Column("checkpoint_id", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("locked_at", sa.DateTime(), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(), nullable=True),
        sa.Column("invalidation_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["stage_run_id"], ["stage_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supersedes_id"], ["artifact_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["checkpoint_id"], ["project_checkpoints.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("version > 0", name="ck_artifact_versions_version_positive"),
        sa.CheckConstraint("byte_size >= 0", name="ck_artifact_versions_size_nonnegative"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "artifact_id",
            "version",
            name="uq_artifact_versions_artifact_version",
        ),
    )
    op.create_index(
        "ix_artifact_versions_stage_status",
        "artifact_versions",
        ["stage_run_id", "status", "version"],
    )

    op.create_table(
        "quality_gate_runs",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("project_id", sa.String(80), nullable=False),
        sa.Column("workflow_id", sa.String(80), nullable=False),
        sa.Column("stage_run_id", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("resolution", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["stage_run_id"], ["stage_runs.id"], ondelete="CASCADE"),
        sa.CheckConstraint("version > 0", name="ck_quality_gate_runs_version_positive"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_quality_gate_runs_stage",
        "quality_gate_runs",
        ["stage_run_id", "evaluated_at"],
    )

    op.create_table(
        "quality_gate_issues",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("gate_run_id", sa.String(80), nullable=False),
        sa.Column("code", sa.String(120), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["gate_run_id"], ["quality_gate_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gate_run_id", "code", name="uq_quality_gate_issues_gate_code"),
    )

    op.create_table(
        "quality_gate_artifacts",
        sa.Column("gate_run_id", sa.String(80), nullable=False),
        sa.Column("artifact_version_id", sa.String(80), nullable=False),
        sa.ForeignKeyConstraint(["gate_run_id"], ["quality_gate_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["artifact_version_id"], ["artifact_versions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("gate_run_id", "artifact_version_id"),
    )

    op.create_table(
        "handoff_packets",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("project_id", sa.String(80), nullable=False),
        sa.Column("workflow_id", sa.String(80), nullable=False),
        sa.Column("from_stage_run_id", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("from_stage", sa.String(20), nullable=False),
        sa.Column("to_stage", sa.String(20), nullable=True),
        sa.Column("gate_run_id", sa.String(80), nullable=False),
        sa.Column("checkpoint_id", sa.String(80), nullable=False),
        sa.Column("artifact_version_ids", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("invalidated_at", sa.DateTime(), nullable=True),
        sa.Column("invalidation_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["from_stage_run_id"], ["stage_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["gate_run_id"], ["quality_gate_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["checkpoint_id"], ["project_checkpoints.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gate_run_id", name="uq_handoff_packets_gate"),
    )
    op.create_index(
        "ix_handoff_packets_workflow_status",
        "handoff_packets",
        ["workflow_id", "status", "created_at"],
    )

    op.create_table(
        "change_requests",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("project_id", sa.String(80), nullable=False),
        sa.Column("workflow_id", sa.String(80), nullable=False),
        sa.Column("source_stage_run_id", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("target_stage", sa.String(20), nullable=False),
        sa.Column("gate_run_id", sa.String(80), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("input_artifact_version_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_stage_run_id"], ["stage_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["gate_run_id"], ["quality_gate_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_change_requests_workflow_status",
        "change_requests",
        ["workflow_id", "status", "created_at"],
    )

    op.create_table(
        "recovery_records",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("project_id", sa.String(80), nullable=False),
        sa.Column("workflow_id", sa.String(80), nullable=False),
        sa.Column("stage_run_id", sa.String(80), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("interrupted_tasks", sa.Integer(), nullable=False),
        sa.Column("interrupted_agent_runs", sa.Integer(), nullable=False),
        sa.Column("interrupted_tool_calls", sa.Integer(), nullable=False),
        sa.Column("detected_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["stage_run_id"], ["stage_runs.id"], ondelete="SET NULL"),
        sa.CheckConstraint("interrupted_tasks >= 0", name="ck_recovery_tasks_nonnegative"),
        sa.CheckConstraint(
            "interrupted_agent_runs >= 0", name="ck_recovery_agent_runs_nonnegative"
        ),
        sa.CheckConstraint(
            "interrupted_tool_calls >= 0", name="ck_recovery_tool_calls_nonnegative"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_recovery_records_status",
        "recovery_records",
        ["status", "detected_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_recovery_records_status", table_name="recovery_records")
    op.drop_table("recovery_records")
    op.drop_index("ix_change_requests_workflow_status", table_name="change_requests")
    op.drop_table("change_requests")
    op.drop_index("ix_handoff_packets_workflow_status", table_name="handoff_packets")
    op.drop_table("handoff_packets")
    op.drop_table("quality_gate_artifacts")
    op.drop_table("quality_gate_issues")
    op.drop_index("ix_quality_gate_runs_stage", table_name="quality_gate_runs")
    op.drop_table("quality_gate_runs")
    op.drop_index("ix_artifact_versions_stage_status", table_name="artifact_versions")
    op.drop_table("artifact_versions")
    op.drop_index("ix_artifacts_workflow_stage", table_name="artifacts")
    op.drop_table("artifacts")
    op.drop_index("ix_tool_calls_workflow_status", table_name="tool_calls")
    op.drop_table("tool_calls")
    op.drop_index("ix_approvals_workflow_status", table_name="approvals")
    op.drop_table("approvals")
    op.drop_index("ix_capability_requests_workflow_status", table_name="capability_requests")
    op.drop_table("capability_requests")
    op.drop_column("workflows", "execution_mode")
