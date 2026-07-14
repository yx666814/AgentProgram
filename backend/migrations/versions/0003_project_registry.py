"""Add the Stage 2 project and workspace registry."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from agent_platform.infrastructure.database.schema import (
    PROJECT_REGISTRY_DATABASE_REVISION,
    RELIABLE_OUTBOX_DATABASE_REVISION,
)

revision: str = PROJECT_REGISTRY_DATABASE_REVISION
down_revision: str | None = RELIABLE_OUTBOX_DATABASE_REVISION
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_projects_version_positive"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_projects_updated_at", "projects", ["updated_at"])
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("project_id", sa.String(80), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("root_path", sa.Text(), nullable=False),
        sa.Column("canonical_root_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", name="uq_workspaces_project_id"),
        sa.UniqueConstraint(
            "canonical_root_path",
            name="uq_workspaces_canonical_root_path",
        ),
    )
    op.create_index("ix_workspaces_mode", "workspaces", ["mode"])
    op.create_table(
        "project_manifests",
        sa.Column("project_id", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("manifest_version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("document", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id"),
    )
    op.create_table(
        "project_instructions",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("project_id", sa.String(80), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "relative_path",
            name="uq_project_instructions_project_path",
        ),
    )
    op.create_index(
        "ix_project_instructions_project_id",
        "project_instructions",
        ["project_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_project_instructions_project_id",
        table_name="project_instructions",
    )
    op.drop_table("project_instructions")
    op.drop_table("project_manifests")
    op.drop_index("ix_workspaces_mode", table_name="workspaces")
    op.drop_table("workspaces")
    op.drop_index("ix_projects_updated_at", table_name="projects")
    op.drop_table("projects")
