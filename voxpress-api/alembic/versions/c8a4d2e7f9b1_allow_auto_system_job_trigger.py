"""allow auto system job trigger

Revision ID: c8a4d2e7f9b1
Revises: b9c2d6e4f1a0
Create Date: 2026-04-24 16:20:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c8a4d2e7f9b1"
down_revision: Union[str, Sequence[str], None] = "b9c2d6e4f1a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_system_job_runs_trigger_kind",
        "system_job_runs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_system_job_runs_trigger_kind",
        "system_job_runs",
        "trigger_kind IN ('scheduled','manual','auto')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_system_job_runs_trigger_kind",
        "system_job_runs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_system_job_runs_trigger_kind",
        "system_job_runs",
        "trigger_kind IN ('scheduled','manual')",
    )
