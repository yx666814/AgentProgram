"""Persist external changes and three-way file conflicts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from agent_platform.infrastructure.database.schema import (
    PROJECT_CHECKPOINT_DATABASE_REVISION,
    PROJECT_CONFLICT_DATABASE_REVISION,
)

revision: str = PROJECT_CONFLICT_DATABASE_REVISION
down_revision: str | None = PROJECT_CHECKPOINT_DATABASE_REVISION
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "external_changes",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("project_id", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("change_type", sa.String(20), nullable=False),
        sa.Column("baseline_content_hash", sa.String(64), nullable=True),
        sa.Column("current_content_hash", sa.String(64), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("detected_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_external_changes_open",
        "external_changes",
        ["project_id", "status", "detected_at"],
    )
    op.create_table(
        "file_conflicts",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("project_id", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("baseline_content_hash", sa.String(64), nullable=True),
        sa.Column("user_content_hash", sa.String(64), nullable=True),
        sa.Column("agent_content_hash", sa.String(64), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("resolution", sa.String(20), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.CheckConstraint("version > 0", name="ck_file_conflicts_version_positive"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_file_conflicts_open",
        "file_conflicts",
        ["project_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_file_conflicts_open", table_name="file_conflicts")
    op.drop_table("file_conflicts")
    op.drop_index("ix_external_changes_open", table_name="external_changes")
    op.drop_table("external_changes")
