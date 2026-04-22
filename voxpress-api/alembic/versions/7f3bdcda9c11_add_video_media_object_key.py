"""add media_object_key to videos

Revision ID: 7f3bdcda9c11
Revises: a4fbe9d2d5c4
Create Date: 2026-04-21 09:48:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7f3bdcda9c11"
down_revision: Union[str, Sequence[str], None] = "a4fbe9d2d5c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("media_object_key", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("videos", "media_object_key")
