"""add avatar_url to creators

Revision ID: a4fbe9d2d5c4
Revises: 0acaea999e7e
Create Date: 2026-04-20 16:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a4fbe9d2d5c4"
down_revision: Union[str, Sequence[str], None] = "0acaea999e7e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("creators", sa.Column("avatar_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("creators", "avatar_url")
