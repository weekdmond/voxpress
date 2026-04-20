"""add idx_tasks_creator

Revision ID: 0acaea999e7e
Revises: 98faa810d482
Create Date: 2026-04-20 13:27:46.033239

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0acaea999e7e'
down_revision: Union[str, Sequence[str], None] = '98faa810d482'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("idx_tasks_creator", "tasks", ["creator_id"])


def downgrade() -> None:
    op.drop_index("idx_tasks_creator", table_name="tasks")
