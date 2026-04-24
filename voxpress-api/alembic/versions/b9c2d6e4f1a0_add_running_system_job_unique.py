"""add running system job unique index

Revision ID: b9c2d6e4f1a0
Revises: f6e1a7c9b2d4
Create Date: 2026-04-24 10:20:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b9c2d6e4f1a0"
down_revision: Union[str, Sequence[str], None] = "f6e1a7c9b2d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_system_job_runs_running_job_key",
        "system_job_runs",
        ["job_key"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index("uq_system_job_runs_running_job_key", table_name="system_job_runs")
