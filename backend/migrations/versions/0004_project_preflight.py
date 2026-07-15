"""Persist project preflight evidence."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from agent_platform.infrastructure.database.schema import (
    PROJECT_PREFLIGHT_DATABASE_REVISION,
    PROJECT_REGISTRY_DATABASE_REVISION,
)

revision: str = PROJECT_PREFLIGHT_DATABASE_REVISION
down_revision: str | None = PROJECT_REGISTRY_DATABASE_REVISION
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_preflight_runs",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("project_id", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("manifest_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("checks", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_project_preflight_runs_latest",
        "project_preflight_runs",
        ["project_id", "completed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_project_preflight_runs_latest",
        table_name="project_preflight_runs",
    )
    op.drop_table("project_preflight_runs")
