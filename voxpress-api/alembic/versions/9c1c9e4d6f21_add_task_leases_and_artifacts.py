"""add task leases and artifacts

Revision ID: 9c1c9e4d6f21
Revises: f2c4b8c1a9de
Create Date: 2026-04-21 14:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "9c1c9e4d6f21"
down_revision: Union[str, Sequence[str], None] = "f2c4b8c1a9de"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(
        "tasks",
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.add_column("tasks", sa.Column("lease_owner", sa.Text(), nullable=True))
    op.add_column("tasks", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tasks", sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("idx_tasks_stage_ready", "tasks", ["stage", "status", "run_after"], unique=False)

    op.create_table(
        "task_artifacts",
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transcript_segments", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("organized", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id"),
    )

    op.alter_column("tasks", "attempt_count", server_default=None)
    op.alter_column("tasks", "run_after", server_default=None)


def downgrade() -> None:
    op.drop_table("task_artifacts")
    op.drop_index("idx_tasks_stage_ready", table_name="tasks")
    op.drop_column("tasks", "last_heartbeat_at")
    op.drop_column("tasks", "lease_expires_at")
    op.drop_column("tasks", "lease_owner")
    op.drop_column("tasks", "run_after")
    op.drop_column("tasks", "attempt_count")
