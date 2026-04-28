"""allow auto task trigger

Revision ID: e2a9b7c4d1f0
Revises: c8a4d2e7f9b1
Create Date: 2026-04-25 09:30:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e2a9b7c4d1f0"
down_revision: Union[str, Sequence[str], None] = "c8a4d2e7f9b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_tasks_trigger_kind",
        "tasks",
        type_="check",
    )
    op.create_check_constraint(
        "ck_tasks_trigger_kind",
        "tasks",
        "trigger_kind IN ('manual','batch','rerun','auto')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_tasks_trigger_kind",
        "tasks",
        type_="check",
    )
    op.create_check_constraint(
        "ck_tasks_trigger_kind",
        "tasks",
        "trigger_kind IN ('manual','batch','rerun')",
    )
