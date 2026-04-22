"""add task runs and task metrics

Revision ID: d4b8f9a1c2e3
Revises: c3f4a7d8b912
Create Date: 2026-04-22 11:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d4b8f9a1c2e3"
down_revision: Union[str, Sequence[str], None] = "c3f4a7d8b912"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.add_column(
        "tasks",
        sa.Column("trigger_kind", sa.Text(), nullable=False, server_default="manual"),
    )
    op.add_column("tasks", sa.Column("rerun_of_task_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("tasks", sa.Column("resume_from_stage", sa.Text(), nullable=True))
    op.add_column("tasks", sa.Column("elapsed_ms", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("tasks", sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("tasks", sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(
        "tasks",
        sa.Column("cost_cny", sa.Numeric(12, 4), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_tasks_trigger_kind",
        "tasks",
        "trigger_kind IN ('manual','batch','rerun')",
    )
    op.create_foreign_key(
        "fk_tasks_rerun_of_task_id_tasks",
        "tasks",
        "tasks",
        ["rerun_of_task_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_tasks_rerun_of", "tasks", ["rerun_of_task_id"], unique=False)

    op.create_table(
        "task_stage_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("provider", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_cny", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "stage IN ('download','transcribe','correct','organize','save')",
            name="ck_task_stage_runs_stage",
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','done','failed','canceled','skipped')",
            name="ck_task_stage_runs_status",
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "stage", name="uq_task_stage_runs_task_stage"),
    )
    op.create_index("idx_task_stage_runs_task", "task_stage_runs", ["task_id"], unique=False)
    op.create_index("idx_task_stage_runs_model", "task_stage_runs", ["model"], unique=False)

    op.execute(
        """
        INSERT INTO task_stage_runs (
            id,
            task_id,
            stage,
            status,
            started_at,
            finished_at,
            duration_ms,
            detail,
            error
        )
        SELECT
            gen_random_uuid(),
            t.id,
            t.stage,
            CASE
                WHEN t.status = 'done' THEN 'done'
                WHEN t.status = 'failed' THEN 'failed'
                WHEN t.status = 'canceled' THEN 'canceled'
                WHEN t.status = 'running' THEN 'running'
                ELSE 'queued'
            END,
            t.started_at,
            t.finished_at,
            CASE
                WHEN t.finished_at IS NOT NULL THEN GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (t.finished_at - t.started_at)) * 1000))::int
                ELSE NULL
            END,
            t.detail,
            t.error
        FROM tasks t
        """
    )

    op.execute(
        """
        UPDATE tasks
        SET elapsed_ms = CASE
            WHEN finished_at IS NOT NULL THEN GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (finished_at - started_at)) * 1000))::int
            ELSE NULL
        END
        """
    )

    op.alter_column("tasks", "trigger_kind", server_default=None)
    op.alter_column("tasks", "input_tokens", server_default=None)
    op.alter_column("tasks", "output_tokens", server_default=None)
    op.alter_column("tasks", "total_tokens", server_default=None)
    op.alter_column("tasks", "cost_cny", server_default=None)
    op.alter_column("task_stage_runs", "status", server_default=None)
    op.alter_column("task_stage_runs", "input_tokens", server_default=None)
    op.alter_column("task_stage_runs", "output_tokens", server_default=None)
    op.alter_column("task_stage_runs", "total_tokens", server_default=None)
    op.alter_column("task_stage_runs", "cost_cny", server_default=None)


def downgrade() -> None:
    op.drop_index("idx_task_stage_runs_model", table_name="task_stage_runs")
    op.drop_index("idx_task_stage_runs_task", table_name="task_stage_runs")
    op.drop_table("task_stage_runs")
    op.drop_index("idx_tasks_rerun_of", table_name="tasks")
    op.drop_constraint("fk_tasks_rerun_of_task_id_tasks", "tasks", type_="foreignkey")
    op.drop_constraint("ck_tasks_trigger_kind", "tasks", type_="check")
    op.drop_column("tasks", "cost_cny")
    op.drop_column("tasks", "total_tokens")
    op.drop_column("tasks", "output_tokens")
    op.drop_column("tasks", "input_tokens")
    op.drop_column("tasks", "elapsed_ms")
    op.drop_column("tasks", "resume_from_stage")
    op.drop_column("tasks", "rerun_of_task_id")
    op.drop_column("tasks", "trigger_kind")
