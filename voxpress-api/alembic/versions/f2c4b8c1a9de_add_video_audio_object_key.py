"""add audio_object_key to videos

Revision ID: f2c4b8c1a9de
Revises: e6a9d96e6c27
Create Date: 2026-04-21 13:05:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f2c4b8c1a9de"
down_revision: Union[str, Sequence[str], None] = "e6a9d96e6c27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("audio_object_key", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("videos", "audio_object_key")
