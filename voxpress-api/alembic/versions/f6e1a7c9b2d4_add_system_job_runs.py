"""add system job runs

Revision ID: f6e1a7c9b2d4
Revises: d4b8f9a1c2e3
Create Date: 2026-04-23 12:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f6e1a7c9b2d4"
down_revision: Union[str, Sequence[str], None] = "d4b8f9a1c2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.create_table(
        "system_job_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_key", sa.Text(), nullable=False),
        sa.Column("job_name", sa.Text(), nullable=False),
        sa.Column("trigger_kind", sa.Text(), nullable=False, server_default="scheduled"),
        sa.Column("status", sa.Text(), nullable=False, server_default="running"),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("total_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running','done','failed','skipped')",
            name="ck_system_job_runs_status",
        ),
        sa.CheckConstraint(
            "trigger_kind IN ('scheduled','manual')",
            name="ck_system_job_runs_trigger_kind",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_system_job_runs_status", "system_job_runs", ["status", "started_at"], unique=False)
    op.create_index("idx_system_job_runs_job_key", "system_job_runs", ["job_key", "started_at"], unique=False)

    op.alter_column("system_job_runs", "trigger_kind", server_default=None)
    op.alter_column("system_job_runs", "total_items", server_default=None)
    op.alter_column("system_job_runs", "processed_items", server_default=None)
    op.alter_column("system_job_runs", "failed_items", server_default=None)
    op.alter_column("system_job_runs", "skipped_items", server_default=None)
    op.alter_column("system_job_runs", "status", server_default=None)


def downgrade() -> None:
    op.drop_index("idx_system_job_runs_job_key", table_name="system_job_runs")
    op.drop_index("idx_system_job_runs_status", table_name="system_job_runs")
    op.drop_table("system_job_runs")
