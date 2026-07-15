"""Add content-addressed project checkpoint indexes."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from agent_platform.infrastructure.database.schema import (
    PROJECT_CHECKPOINT_DATABASE_REVISION,
    PROJECT_PREFLIGHT_DATABASE_REVISION,
)

revision: str = PROJECT_CHECKPOINT_DATABASE_REVISION
down_revision: str | None = PROJECT_PREFLIGHT_DATABASE_REVISION
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_checkpoints",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("project_id", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("manifest_version", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(20), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("total_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.CheckConstraint("file_count >= 0", name="ck_project_checkpoints_file_count"),
        sa.CheckConstraint("total_bytes >= 0", name="ck_project_checkpoints_total_bytes"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_project_checkpoints_latest",
        "project_checkpoints",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_project_checkpoints_content_hash",
        "project_checkpoints",
        ["content_hash"],
    )
    op.create_table(
        "checkpoint_files",
        sa.Column("checkpoint_id", sa.String(80), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["checkpoint_id"],
            ["project_checkpoints.id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("byte_size >= 0", name="ck_checkpoint_files_byte_size"),
        sa.PrimaryKeyConstraint("checkpoint_id", "relative_path"),
    )
    op.create_index(
        "ix_checkpoint_files_content_hash",
        "checkpoint_files",
        ["content_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_checkpoint_files_content_hash", table_name="checkpoint_files")
    op.drop_table("checkpoint_files")
    op.drop_index(
        "ix_project_checkpoints_content_hash",
        table_name="project_checkpoints",
    )
    op.drop_index("ix_project_checkpoints_latest", table_name="project_checkpoints")
    op.drop_table("project_checkpoints")
